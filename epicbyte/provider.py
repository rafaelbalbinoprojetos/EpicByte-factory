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


class QuotaExhausted(ProviderUnavailable):
    """Limite de uso da conta do provedor: não é erro da tarefa; a missão pausa e retoma quando liberar."""
    def __init__(self, message, retry_at=None):
        super().__init__(message)
        self.retry_at = retry_at   # datetime local (aware) ou None


def quota_retry_at(message, now=None):
    """Extrai 'try again at 3:32 AM' (ou '15:32') e devolve o próximo horário local correspondente."""
    import re
    from datetime import datetime, timedelta
    match = re.search(r'try again at\s+(\d{1,2}):(\d{2})\s*([AaPp][Mm])?', message or '')
    now = now or datetime.now().astimezone()
    if not match:
        return now + timedelta(hours=1)
    hour, minute, meridiem = int(match[1]), int(match[2]), (match[3] or '').upper()
    if meridiem == 'PM' and hour != 12:
        hour += 12
    if meridiem == 'AM' and hour == 12:
        hour = 0
    target = now.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return target + timedelta(minutes=2)   # margem para o provedor liberar


def is_quota_error(text):
    text = (text or '').lower()
    return 'usage limit' in text or 'usagelimit' in text or 'rate limit' in text and 'try again' in text


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
            detail = str(params.get('error', {}))
            if is_quota_error(detail):
                raise QuotaExhausted('Limite de uso do provedor: ' + detail[:300], quota_retry_at(detail))
            raise ProviderError('Erro no turno: ' + detail)


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
        # write='build': o agente escreve e testa direto no sandbox (escrita só no workspace, .git protegido, sem rede).
        # write=True: modo legado, o agente devolve edições e o escritor fixo as aplica.
        build = write == 'build'
        if write:
            from .safety import IsolationPolicy
            IsolationPolicy().require_write(workspace)
        if build:
            prompt += ('\nVocê está num sandbox com escrita no workspace e sem rede: escreva os arquivos com suas ferramentas, '
                       'rode os testes e verificações do projeto e corrija até passarem. Ao final, responda somente o JSON pedido.')
        elif write:
            prompt += '\nRetorne JSON com summary, files, issues e edits: [{"path":"caminho relativo","content":"conteudo completo"}]. Nao escreva por ferramentas. Somente criacao/substituicao via edits; comandos e exclusoes recusados.'
        deadline = time.monotonic() + timeout
        process = subprocess.Popen(codex_command() + ['app-server'], cwd=workspace,
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, encoding='utf-8', bufsize=1)
        rpc = Rpc(process)
        try:
            rpc.request('initialize', {'clientInfo': {'name': 'epicbyte-factory', 'version': '1.0.0'}, 'capabilities': None}, deadline, cancelled)
            rpc.send({'jsonrpc': '2.0', 'method': 'initialized', 'params': {}})
            thread_params = {'cwd': str(workspace), 'approvalPolicy': 'never', 'sandbox': 'workspace-write' if build else 'read-only'}
            sandbox_policy = ({'type': 'workspaceWrite', 'writableRoots': [str(workspace)], 'networkAccess': False} if build
                              else {'type': 'readOnly', 'networkAccess': False})
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
            turn = rpc.request('turn/start', {'threadId': thread, 'sandboxPolicy': sandbox_policy, 'input': inputs}, deadline, cancelled)['turn']['id']
            result = collect_turn(rpc, thread, turn, deadline, cancelled)
            result.provider = 'codex-app-server'
            if write and not build:
                from .executor import object_report
                from .write_backend import apply_edits
                if cancelled():
                    raise ProviderError('Execução pausada antes da escrita')
                report = object_report(result.text)
                edits = report.get('edits')
                report['files'] = apply_edits(workspace, edits) if edits else []   # nada a mudar: segue para revisão
                result.text = json.dumps(report, ensure_ascii=False)
            return result
        finally:
            stop_process(process)
