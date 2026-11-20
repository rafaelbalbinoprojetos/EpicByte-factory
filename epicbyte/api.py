"""Local Mission Control API; Python remains the execution authority."""
import os
import hmac
import sqlite3
from .studio import Studio, capabilities
import json
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
from .storage import Store, clean, now
from .model import AGENTS
from .cli import status, create_mission
from .safety import within, IsolationPolicy


def fixed_password(root):
    """Senha fixa opcional: variável EPICBYTE_PASSWORD ou .factory/senha.txt (fora do Git).
    Sem nenhuma das duas, cada inicialização gera uma chave aleatória."""
    value = os.environ.get('EPICBYTE_PASSWORD', '').strip()
    if not value:
        try:
            value = (Path(root) / '.factory' / 'senha.txt').read_text(encoding='utf-8').strip()
        except OSError:
            value = ''
    return value or None


def make_server(db, root, port=8780):
    root = Path(root).resolve()
    initial = Store(db)
    try: Studio(initial, root)
    finally: initial.db.close()
    access = fixed_password(root) or secrets.token_urlsafe(32)
    workers = {}
    gate = threading.Lock()
    studio_gate = threading.Lock()
    creation_gate = threading.Lock()
    stopping = threading.Event()
    diagnostic = {'isolation_certified': False, 'ready_write': False, 'message': 'Diagnóstico atual ainda não executado'}

    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def reply(self, data, code=200):
            body = json.dumps(clean(data), ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def allowed(self, mutable=False):
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                return False
            supplied = self.headers.get('Authorization', '')
            if not hmac.compare_digest(supplied, 'Bearer ' + access):
                return False
            incoming = self.headers.get('Origin')
            expected = f'http://127.0.0.1:{self.server.server_port}'
            return incoming == expected if mutable else incoming in (None, expected)

        def open_store(self):
            try: return Store(db, initialize=False)
            except sqlite3.Error:
                self.reply({'error':'Banco local indisponível; tente novamente'},503)
                return None
        def do_GET(self):
            path = urlsplit(self.path).path
            if not path.startswith('/api/'):
                # Preserve the original read-only routes with their original origin guard.
                if path.startswith('/missions'):
                    if self.headers.get('Origin') or self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
                        return self.reply({'error': 'Forbidden'}, 403)
                    with_store = self.open_store()
                    if with_store is None: return
                    try:
                        parts = path.strip('/').split('/')
                        if len(parts) == 1: return self.reply(status(with_store))
                        if len(parts) == 2: return self.reply(status(with_store, parts[1]))
                        if len(parts) == 3 and parts[2] == 'events':
                            with_store.mission(parts[1])
                            return self.reply([dict(r) for r in with_store.db.execute('SELECT * FROM events WHERE mission=? ORDER BY seq', (parts[1],))])
                        return self.reply({'error': 'Not found'}, 404)
                    except ValueError as error: return self.reply({'error': str(error)}, 404)
                    finally: with_store.db.close()
                return self.static(path)
            if not self.allowed(): return self.reply({'error': 'Autenticação local exigida'}, 403)
            store = self.open_store()
            if store is None: return
            try:
                if path == '/api/state':
                    missions = [status(store, m['id']) for m in status(store)]
                    executions = [dict(r) for r in store.db.execute('SELECT * FROM executions ORDER BY id DESC')]
                    events = [dict(r) for r in store.db.execute('SELECT * FROM events ORDER BY seq DESC LIMIT 300')]
                    evidence = [dict(r) for r in store.db.execute('SELECT * FROM evidence')]
                    studio = Studio(store, root, initialize=False)
                    briefs = [studio.get(r[0]) for r in store.db.execute('SELECT id FROM briefs ORDER BY created DESC LIMIT 100')]
                    agents = [{'name': a, 'responsibilities': (root / 'agents' / (a + '.md')).read_text(encoding='utf-8')} for a in AGENTS]
                    return self.reply(dict(missions=missions, executions=executions, events=events, evidence=evidence, agents=agents, diagnostic=diagnostic, workspaces=[{'id': 'managed', 'label': 'Workspace novo isolado / develop'}], briefs=briefs, capabilities=capabilities(), discovery_runs=[dict(r) for r in store.db.execute('SELECT * FROM discovery_runs ORDER BY id DESC LIMIT 300')], versions={'factory':'2.1', 'python':sys.version.split()[0]}, limits={'max_executions':100,'mission_timeout':3600,'agent_timeout':180}))
                if path == '/api/capabilities': return self.reply(capabilities(probe=True))
                parts = path.strip('/').split('/')
                if len(parts) >= 3 and parts[:2] == ['api','briefs']:
                    studio = Studio(store, root, initialize=False)
                    if len(parts) == 3: return self.reply(studio.get(parts[2]))
                    if len(parts) == 5 and parts[3] == 'references': return self.reply(studio.image(parts[2],parts[4]))
                if path == '/api/events':
                    query = parse_qs(urlsplit(self.path).query)
                    cursor = int(query.get('after', ['0'])[0])
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/event-stream')
                    self.send_header('Cache-Control', 'no-store')
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    deadline = time.monotonic() + 20
                    while True:
                        rows = [dict(r) for r in store.db.execute('SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT 300', (cursor,))]
                        body = 'retry: 2000\n' + ''.join(f'id: {r["seq"]}\ndata: {json.dumps(clean(r))}\n\n' for r in rows) + ': heartbeat\n\n'
                        try:
                            self.wfile.write(body.encode())
                            self.wfile.flush()
                        except (BrokenPipeError, ConnectionResetError):
                            return
                        if rows: cursor = rows[-1]['seq']
                        if stopping.is_set() or 'once' in query or time.monotonic() >= deadline: return
                        time.sleep(1)
                return self.reply({'error':'Not found'},404)
            except (ValueError, OSError) as error: self.reply({'error':str(error)},400)
            except sqlite3.Error: self.reply({'error':'Base local ocupada ou indisponível; tente novamente'},503)
            finally: store.db.close()

        def static(self, path):
            if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}': return self.reply({'error':'Forbidden'},403)
            base = root / 'frontend/dist'
            try:
                file = within(base, base / (path.lstrip('/') or 'index.html'))
                if not file.is_file(): file = base / 'index.html'
                body = file.read_bytes()
                import mimetypes
                self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(file)[0] or 'application/octet-stream')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'")
                self.send_header('Referrer-Policy','no-referrer')
                self.send_header('Content-Length',str(len(body)))
                self.end_headers(); self.wfile.write(body)
            except (RuntimeError, OSError): self.reply({'error':'Execute o build do frontend'},404)

        def do_POST(self):
            if urlsplit(self.path).path == '/api/missions':
                with creation_gate, studio_gate:
                    return self.post()
            return self.post()
        def post(self):
            if not self.allowed(True): return self.reply({'error':'Origem e autenticação local exigidas'},403)
            if self.headers.get('Content-Type') != 'application/json': return self.reply({'error':'JSON exigido'},415)
            store = self.open_store()
            if store is None: return
            try:
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= (7200000 if '/references' in self.path else 200000): raise ValueError('Tamanho inválido')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict): raise ValueError('Objeto JSON exigido')
                path = urlsplit(self.path).path
                if path == '/api/briefs':
                    return self.reply(Studio(store,root,initialize=False).create(data.get('idea')),201)
                parts = path.strip('/').split('/')
                if len(parts) == 4 and parts[:2] == ['api','briefs']:
                    if not studio_gate.acquire(blocking=False): return self.reply({'error':'Concepção em andamento; aguarde e tente novamente'},409)
                    try:
                        studio=Studio(store,root,initialize=False)
                        ident,action=parts[2:]
                        if action == 'analyze': return self.reply(studio.analyze(ident,root,cancelled=stopping.is_set))
                        if action == 'save': return self.reply(studio.save(ident,data.get('proposal'),data.get('version')))
                        if action == 'approve': return self.reply(studio.approve(ident,data.get('version'),data.get('selected'),data.get('design_approved')))
                        if action == 'references': return self.reply(studio.upload(ident,data),201)
                        if action == 'remove-reference': return self.reply(studio.remove(ident,data.get('id')))
                        raise ValueError('Operação de concepção desconhecida')
                    finally: studio_gate.release()
                if path == '/api/diagnostic':
                    from .diagnostics import doctor
                    result = doctor(root, probe=True)
                    diagnostic.clear()
                    diagnostic.update({k: result.get(k) for k in ('authenticated','codex','ready_read_only','isolation_certified','ready_write','write_certification','sandbox_read_only','model_execution_verified','write_reason','actions')})
                    diagnostic['checked_at'] = now()
                    return self.reply(diagnostic)
                if path == '/api/missions':
                    if data.get('workspace') != 'managed': raise ValueError('Workspace não autorizado')
                    for key in ('name','description','criteria'):
                        if not isinstance(data.get(key), str) or not data[key].strip() or len(data[key]) > 30000: raise ValueError('Campo inválido: ' + key)
                    if type(data.get('dry_run', False)) is not bool: raise ValueError('dry_run deve ser booleano')
                    if not isinstance(data.get('constraints', ''), str) or len(data.get('constraints', '')) > 30000: raise ValueError('Restrições inválidas')
                    limits = data.get('limits', {})
                    if not isinstance(limits, dict) or set(limits) - {'mission_timeout','max_executions'}: raise ValueError('Limites inválidos')
                    for key, value in limits.items():
                        if type(value) is not int or not 1 <= value <= {'mission_timeout':3600,'max_executions':100}[key]: raise ValueError('Limite excedido')
                    source = f"# {data['name']}\n\n{data['description']}\n\nCritérios de aceite:\n{data['criteria']}\n\nRestrições:\n{data.get('constraints','')}"
                    if data.get('dry_run') is True: return self.reply({'dry_run':True,'characters':len(source),'message':'Validado sem criar workspace nem chamar provedor'})
                    if data.get('brief_id'):
                        source = Studio(store,root,initialize=False).approved_source(data['brief_id'])
                    # Authorize the current environment before creating a write mission.
                    from .write_backend import certify
                    proof = certify(within(root, root / 'workspaces'))
                    if not proof['certified']: return self.reply({'error':'Isolamento não certificado','certification':proof},409)
                    incoming = root / '.factory/incoming'
                    incoming.mkdir(parents=True,exist_ok=True)
                    file = incoming / (secrets.token_hex(12)+'.md')
                    file.write_text(source,encoding='utf-8')
                    ident = create_mission(store,root,file.relative_to(root))
                    with store.db:
                        store.db.execute('INSERT INTO mission_limits VALUES(?,?)',(ident,json.dumps(limits)))
                        if data.get('brief_id'):
                            store.db.execute('UPDATE briefs SET mission=? WHERE id=? AND mission IS NULL',(ident,data['brief_id']))
                            store.event(ident,'SCOPE_TRANSFERRED',brief=data['brief_id'])
                    return self.reply({'id':ident},201)
                parts = path.strip('/').split('/')
                if len(parts) != 4 or parts[:2] != ['api','missions']: return self.reply({'error':'Not found'},404)
                ident, action = parts[2:]
                mission = store.mission(ident)
                if action == 'pause':
                    if mission['state'] in ('COMPLETED','FAILED'): raise ValueError('Missão terminal')
                    with store.db:
                        store.db.execute('UPDATE missions SET pause=1 WHERE id=?',(ident,)); store.event(ident,'PAUSE_REQUESTED')
                    if not store.db.execute('SELECT 1 FROM locks WHERE mission=?',(ident,)).fetchone() and mission['state'] != 'PAUSED': store.transition(ident,'PAUSED')
                    return self.reply({'pause_requested':ident})
                if action not in ('start','resume'): raise ValueError('Operação desconhecida')
                if mission['state'] not in (('CREATED',) if action == 'start' else ('PAUSED','BLOCKED','FAILED')): raise ValueError('Estado não permite operação')
                IsolationPolicy().require_write(within(within(root, root / 'workspaces'), Path(mission['workspace'])))
                from .diagnostics import doctor
                if not doctor(root)['ready_read_only']: raise ValueError('Codex não autenticado')
                with gate:
                    if ident in workers and workers[ident].poll() is None: raise ValueError('Worker ativo')
                    if store.db.execute('SELECT 1 FROM locks WHERE mission=?',(ident,)).fetchone(): raise ValueError('Lock preservado; use recover-lock na CLI')
                    with store.db:
                        store.db.execute('UPDATE missions SET pause=0 WHERE id=?',(ident,)); store.event(ident,'RESUME_REQUESTED')
                    workers[ident] = subprocess.Popen([sys.executable,'-m','epicbyte.worker',str(db),ident],cwd=root)
                return self.reply({'accepted':ident},202)
            except (ValueError, RuntimeError, OSError) as error: self.reply({'error':str(error)},409)
            except sqlite3.Error: self.reply({'error':'Conflito de persistência; recarregue antes de repetir'},409)
            finally: store.db.close()

        def log_message(self,*args): pass

    class LocalServer(ThreadingHTTPServer):
        request_queue_size = 64
        daemon_threads = False
        def server_close(self):
            stopping.set()
            super().server_close()
    server = LocalServer(('127.0.0.1',port),Handler)
    server.access = access
    server.workers = workers
    return server


def serve(store, port=8780):
    from .cli import ROOT
    db = store.db.execute('PRAGMA database_list').fetchone()[2]
    server = make_server(db,ROOT,port)
    if fixed_password(ROOT):
        print(f'Mission Control: http://127.0.0.1:{port}/  (entre com a senha configurada)',flush=True)
    else:
        print(f'Mission Control: http://127.0.0.1:{port}/#access={server.access}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        # Request cooperative pause first; process cleanup uses the provider tree terminator.
        with store.db:
            for ident in server.workers:
                store.db.execute('UPDATE missions SET pause=1 WHERE id=?', (ident,))
        from .provider import stop_process
        for process in server.workers.values():
            if process.poll() is None:
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired: stop_process(process)
        server.server_close()
