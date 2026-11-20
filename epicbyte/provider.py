"""Local stdio App Server. No API keys, remote fallback or credential reading."""
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from dataclasses import dataclass, field
from .safety import SafetyError


class ProviderError(RuntimeError):
    pass


class IncompleteTurn(ProviderError):
    pass


class ProviderUnavailable(ProviderError):
    pass


@dataclass
class Result:
    text: str
    thread: str
    turn: str
    commands: list = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    provider: str = 'unverified'


class Provider(ABC):
    @abstractmethod
    def execute(self, prompt, workspace, timeout=180, write=False, cancelled=lambda: False):
        """Return only after final completed turn; raise on all other outcomes."""


def codex_command():
    command = shutil.which('codex.cmd' if os.name == 'nt' else 'codex')
    if not command and os.name == 'nt':   # instalação global do npm fora do PATH do processo
        candidate = os.path.join(os.environ.get('APPDATA', ''), 'npm', 'codex.cmd')
        command = candidate if os.path.isfile(candidate) else None
    if not command:
        raise ProviderError('Codex CLI indisponível')
    # Launch the installed JS entry point directly: no shell or .cmd interpolation.
    if os.name == 'nt':
        from pathlib import Path
        # Preserve the installed launcher's environment and package resolution.
        # Calling its native binary directly skips CODEX_MANAGED_PACKAGE_ROOT.
        script = Path(command).parent / 'node_modules/@openai/codex/bin/codex.js'
        adjacent_node = Path(command).parent / 'node.exe'
        default_node = Path(os.environ.get('ProgramFiles', r'C:\Program Files')) / 'nodejs' / 'node.exe'
        node = str(adjacent_node) if adjacent_node.is_file() else shutil.which('node') or (str(default_node) if default_node.is_file() else None)
        if not node or not script.is_file():
            raise ProviderError('Instalação Node do Codex não reconhecida')
        return [node, str(script)]
    return [command]


def stop_process(process):
    """Close only the process tree started by this provider/probe."""
    if process.poll() is None and os.name == 'nt':
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True, timeout=10)
    elif process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=3)
    for stream in (process.stdin, process.stdout, process.stderr):
        if stream is not None:
            stream.close()


class Rpc:
    def __init__(self, process):
        self.process = process
        self.messages = queue.Queue(maxsize=20000)
        self.pending = deque()
        self.counter = 0
        self.reader_error = None
        threading.Thread(target=self._read, daemon=True).start()
        threading.Thread(target=self._drain_stderr, daemon=True).start()

    def _read(self):
        try:
            for line in self.process.stdout:
                try:
                    self.messages.put_nowait(json.loads(line))
                except json.JSONDecodeError:
                    continue
                except queue.Full:
                    self.reader_error = 'Limite de mensagens excedido'
                    break
        except (OSError, ValueError):
            pass

    def _drain_stderr(self):
        # stderr can contain local configuration details; never persist raw output.
        try:
            for _ in self.process.stderr:
                pass
        except (OSError, ValueError):
            pass

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + '\n')
        self.process.stdin.flush()

    def receive(self, deadline, cancelled):
        while time.monotonic() < deadline:
            if cancelled():
                raise ProviderError('Execução pausada')
            if self.reader_error:
                raise ProviderError(self.reader_error)
            try:
                msg = self.messages.get(timeout=min(.2, max(.001, deadline - time.monotonic())))
            except queue.Empty:
                if self.process.poll() is not None:
                    raise IncompleteTurn('App Server encerrou antes do resultado final')
                continue
            if 'method' in msg and 'id' in msg:
                # Deny all server-initiated approval/tool/auth requests.
                self.send({'jsonrpc': '2.0', 'id': msg['id'], 'error': {'code': -32601, 'message': 'Factory denies interactive requests'}})
                raise SafetyError('Operação exige decisão humana: ' + msg['method'])
            return msg
        raise TimeoutError('Timeout do App Server')

    def request(self, method, params, deadline, cancelled=lambda: False):
        self.counter += 1
        ident = self.counter
        self.send({'jsonrpc': '2.0', 'id': ident, 'method': method, 'params': params})
        while True:
            msg = self.receive(deadline, cancelled)
            if msg.get('id') == ident:
                if 'error' in msg:
                    message = str(msg['error'])
                    if any(word in message.lower() for word in ('429', 'quota', 'usage limit', 'rate limit', 'not logged', 'unauthorized', 'authentication')):
                        raise ProviderUnavailable('Provedor indisponível ou cota/autenticação requer atenção; sem fallback')
                    raise ProviderError('RPC ' + method + ': ' + str(msg['error']))
                if 'result' not in msg:
                    raise ProviderError('Resposta RPC sem result')
                return msg['result']
            self.pending.append(msg)

    def next(self, deadline, cancelled):
        return self.pending.popleft() if self.pending else self.receive(deadline, cancelled)


def collect_turn(rpc, thread, turn, deadline, cancelled=lambda: False):
    reports, commands, usage = [], [], {}
    while True:
        msg = rpc.next(deadline, cancelled)
        method, params = msg.get('method'), msg.get('params', {})
        if params.get('threadId', thread) != thread or params.get('turnId', turn) != turn:
            continue
        if method == 'item/completed':
            item = params.get('item', {})
            if item.get('type') == 'agentMessage':
                reports.append(item.get('text', ''))
            elif item.get('type') == 'commandExecution':
                commands.append(item)
        elif method == 'thread/tokenUsage/updated':
            usage = params.get('tokenUsage', {})
        elif method == 'turn/completed':
            final = params.get('turn', {})
            if final.get('id', turn) != turn:
                continue
            if final.get('status') != 'completed':
                raise IncompleteTurn('Turno não concluído: ' + str(final.get('status')))
            if not reports or not reports[-1].strip():
                raise IncompleteTurn('Turno sem relatório final')
            return Result(reports[-1], thread, turn, commands, usage)
        elif method == 'error' and not params.get('willRetry', False):
            raise ProviderError('Erro no turno: ' + str(params.get('error', {})))


class CodexProvider(Provider):
    def capabilities(self):
        process = subprocess.Popen(codex_command() + ['app-server'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        rpc = Rpc(process)
        try:
            deadline = time.monotonic() + 15
            rpc.request('initialize', {'clientInfo': {'name':'epicbyte-capabilities','version':'2.1'},'capabilities':None},deadline)
            rpc.send({'jsonrpc':'2.0','method':'initialized','params':{}})
            result = rpc.request('model/list', {'limit':100}, deadline)
            models = result.get('data', [])
            default = next((m for m in models if m.get('isDefault')), None)
            return {'images':bool(default and 'image' in default.get('inputModalities',[])), 'model':default.get('model') if default else None, 'input_format':'localImage', 'checked_at':time.time()}
        finally:
            stop_process(process)
    def execute(self, prompt, workspace, timeout=180, write=False, cancelled=lambda: False, images=None, model=None):
        if write:
            from .safety import IsolationPolicy
            IsolationPolicy().require_write(workspace)
            prompt += '\nRetorne JSON com summary, files, issues e edits: [{"path":"caminho relativo","content":"conteudo completo"}]. Nao escreva por ferramentas. Somente criacao/substituicao via edits; comandos e exclusoes recusados.'
        deadline = time.monotonic() + timeout
        process = subprocess.Popen(codex_command() + ['app-server'], cwd=workspace,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8', bufsize=1)
        rpc = Rpc(process)
        try:
            rpc.request('initialize', {'clientInfo': {'name': 'epicbyte-factory', 'version': '1.0.0'}, 'capabilities': None}, deadline, cancelled)
            rpc.send({'jsonrpc': '2.0', 'method': 'initialized', 'params': {}})
            thread_params = {'cwd': str(workspace), 'approvalPolicy': 'never', 'sandbox': 'read-only'}
            inputs = [{'type': 'text', 'text': prompt}]
            if images:
                catalog = rpc.request('model/list', {'limit':100}, deadline, cancelled)
                selected = next((m for m in catalog.get('data',[]) if m.get('model') == model), None)
                if write or not selected or 'image' not in selected.get('inputModalities',[]):
                    raise ProviderError('Capacidade multimodal não confirmada para o modelo selecionado')
                if len(images) > 8: raise ProviderError('Limite de imagens excedido')
                thread_params['model'] = model
                inputs += [{'type':'localImage','path':str(path)} for path in images]
            thread = rpc.request('thread/start', thread_params, deadline, cancelled)['thread']['id']
            turn = rpc.request('turn/start', {'threadId': thread, 'sandboxPolicy': {'type': 'readOnly', 'networkAccess': False}, 'input': inputs}, deadline, cancelled)['turn']['id']
            result = collect_turn(rpc, thread, turn, deadline, cancelled)
            result.provider = 'codex-app-server'
            if write:
                from .executor import object_report
                from .write_backend import apply_edits
                if cancelled():
                    raise ProviderError('Execução pausada antes da escrita')
                report = object_report(result.text)
                report['files'] = apply_edits(workspace, report.get('edits'))
                result.text = json.dumps(report, ensure_ascii=False)
            return result
        finally:
            stop_process(process)
