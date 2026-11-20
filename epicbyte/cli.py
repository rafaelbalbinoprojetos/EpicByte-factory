import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from .engine import WorkflowEngine, limits_for
from .model import AGENTS, validate_plan
from .provider import CodexProvider, codex_command
from .safety import GIT, within, SafetyError, validate_git
from .storage import Store, clean

ROOT = Path(__file__).resolve().parent.parent


from .diagnostics import doctor as _doctor

def doctor(root=ROOT, probe=False):
    return _doctor(root, probe=probe)


def mission_input(root, source):
    path = within(root, root / source)
    if not path.is_file() or path.stat().st_size > 200000:
        raise ValueError('Missão ausente ou maior que 200 KB')
    text = path.read_text(encoding='utf-8-sig')
    if not text.strip():
        raise ValueError('Missão vazia')
    return path, text


def create_mission(store, root, source, plan=None, template=None, assets=None):
    _, text = mission_input(root, source)
    ident = 'mission_' + uuid.uuid4().hex[:12]
    workspaces = within(root, root / 'workspaces')
    workspace = within(workspaces, workspaces / ident)
    workspace.mkdir(parents=True, exist_ok=False)
    subprocess.run([GIT, 'init', '-b', 'develop', str(workspace)], check=True, capture_output=True, timeout=15)
    validate_git(workspace)
    if template:
        from .web import prepare_workspace
        try:
            prepare_workspace(workspace, template)
            if assets:
                from .web import commit_task, copy_assets
                used = copy_assets(workspace, assets, root)
                lines = [f"- {u.get('webp', u['path'])} ({u.get('webp_size', [u.get('width'), u.get('height')])[0]}x{u.get('webp_size', [u.get('width'), u.get('height')])[1]}, otimizada; original {u['path']}: {u['original']})" for u in used]
                text = '\n'.join([text, '', 'Imagens fornecidas pelo cliente (já em public/assets/):', *lines])
                commit_task(workspace, 'Imagens fornecidas pelo cliente')
        except Exception:
            shutil.rmtree(workspace, ignore_errors=True)
            raise
    store.create(ident, text, workspace)
    if plan is not None:
        store.save_plan(ident, plan)
    return ident


def status(store, ident=None):
    if ident:
        m = store.mission(ident)
        return {**m, 'tasks': store.tasks(ident)}
    return [dict(r) for r in store.db.execute('SELECT id,state,created,elapsed,workspace FROM missions ORDER BY created DESC')]


def main(argv=None):
    parser = argparse.ArgumentParser(description='EpicByte Factory 1.0 — execução local segura')
    parser.add_argument('--db', default=str(ROOT / '.factory/factory.sqlite3'))
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ('run', 'dry-run'):
        p = sub.add_parser(command)
        p.add_argument('mission')
        p.add_argument('--plan', help='Plano JSON existente validado antes da execução')
    p = sub.add_parser('status')
    p.add_argument('mission_id', nargs='?')
    for command in ('resume', 'pause', 'logs', 'recover-lock'):
        sub.add_parser(command).add_argument('mission_id')
    sub.add_parser('agents')
    sub.add_parser('doctor').add_argument('--probe', action='store_true', help='Testar App Server/account e comando sandbox sem chamar modelo')
    api = sub.add_parser('serve')
    api.add_argument('--port', type=int, default=8780)
    args = parser.parse_args(argv)
    try:
        if args.command == 'doctor':
            result = doctor(probe=args.probe)
            print(json.dumps(clean(result), ensure_ascii=False, indent=2))
            return 0 if result['ready_write'] else 2
        if args.command == 'agents':
            print(json.dumps([{'agent': a, 'instructions': str(ROOT / 'agents' / (a+'.md'))} for a in AGENTS], indent=2))
            return 0
        if args.command in ('run', 'dry-run'):
            path, text = mission_input(ROOT, args.mission)
            plan = None
            if args.plan:
                plan_path = within(ROOT, ROOT / args.plan)
                plan = validate_plan(json.loads(plan_path.read_text(encoding='utf-8-sig')))
            if args.command == 'dry-run':
                print(json.dumps({'mission': str(path), 'characters': len(text), 'plan_valid': plan is not None,
                                  'task_count': len(plan['tasks']) if plan else None,
                                  'mode': 'sem chamadas ao provedor ou escrita de workspace',
                                  'write_execution': 'bloqueada até isolamento certificado'}, ensure_ascii=False, indent=2))
                return 0
        db_path = within(ROOT, Path(args.db))
        db_path.parent.mkdir(parents=True, exist_ok=True)
        store = Store(db_path)
        try:
            if args.command == 'serve':
                from .api import serve
                serve(store, args.port)
                return 0
            if args.command == 'run':
                ident = create_mission(store, ROOT, args.mission, plan)
                print('Mission:', ident, flush=True)
                # Authentication is checked before any calls that might consume quota.
                if not doctor()['ready_read_only']:
                    store.transition(ident, 'BLOCKED')
                    with store.db:
                        store.event(ident, 'MISSION_BLOCKED', reason='Codex local indisponível ou não autenticado neste processo')
                else:
                    WorkflowEngine(store, CodexProvider(), ROOT / 'agents', limits=limits_for(store, ident)).run(ident)
                print(json.dumps(clean(status(store, ident)), ensure_ascii=False, indent=2))
                return 0 if store.mission(ident)['state'] == 'COMPLETED' else 2
            ident = getattr(args, 'mission_id', None)
            if args.command == 'status':
                result = status(store, ident)
            elif args.command == 'logs':
                store.mission(ident)
                result = [dict(r) for r in store.db.execute('SELECT * FROM events WHERE mission=? ORDER BY seq', (ident,))]
            elif args.command == 'pause':
                state = store.mission(ident)['state']
                if state in ('COMPLETED', 'FAILED'):
                    raise ValueError('Missão terminal')
                with store.db:
                    store.db.execute('UPDATE missions SET pause=1 WHERE id=?', (ident,))
                    store.event(ident, 'PAUSE_REQUESTED')
                if not store.db.execute('SELECT 1 FROM locks WHERE mission=?', (ident,)).fetchone() and state != 'PAUSED':
                    store.transition(ident, 'PAUSED')
                result = {'pause_requested': ident}
            elif args.command == 'recover-lock':
                store.mission(ident)
                lock = store.db.execute('SELECT owner FROM locks WHERE mission=?', (ident,)).fetchone()
                if lock:
                    pid = int(lock[0])
                    # Do not signal a process on Windows: os.kill(pid,0) is not a portable liveness probe there.
                    if os.name == 'nt':
                        probe = subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/FO', 'CSV', '/NH'], capture_output=True, text=True, timeout=10)
                        if probe.returncode or re.search(r'"' + str(pid) + r'"', probe.stdout):
                            raise ValueError('PID existe ou não pôde ser verificado; lock preservado')
                    else:
                        try:
                            os.kill(pid, 0)
                        except ProcessLookupError:
                            pass
                        else:
                            raise ValueError('PID ainda existe; lock preservado')
                    with store.db:
                        store.db.execute('DELETE FROM locks WHERE mission=?', (ident,))
                        store.event(ident, 'STALE_LOCK_RECOVERED', pid=pid)
                result = {'lock_recovered': ident}
            elif args.command == 'resume':
                store.mission(ident)
                if not doctor()['ready_read_only']:
                    raise ValueError('Codex local indisponível ou não autenticado')
                with store.db:
                    store.db.execute('UPDATE missions SET pause=0 WHERE id=?', (ident,))
                    store.event(ident, 'RESUME_REQUESTED')
                WorkflowEngine(store, CodexProvider(), ROOT / 'agents', limits=limits_for(store, ident)).run(ident)
                result = status(store, ident)
            else:
                raise ValueError('Comando desconhecido')
            print(json.dumps(clean(result), ensure_ascii=False, indent=2))
            return 2 if args.command == 'resume' and result['state'] != 'COMPLETED' else 0
        finally:
            store.db.close()
    except (ValueError, RuntimeError, OSError) as error:
        print(json.dumps({'error': clean(str(error))}, ensure_ascii=False), file=sys.stderr)
        return 2
