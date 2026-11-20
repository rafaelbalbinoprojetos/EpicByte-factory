"""Host diagnostics: no credential files, login flows or security mutations."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib

from .provider import codex_command, Rpc, stop_process
from .safety import SafetyError, validate_git
from .storage import clean


def command(args, cwd):
    try:
        result = subprocess.run(args, cwd=cwd, capture_output=True, text=True,
                                encoding='utf-8', errors='replace', timeout=20)
        return clean({'command': args, 'cwd': str(cwd), 'exit_code': result.returncode,
                      'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()})
    except (OSError, subprocess.TimeoutExpired) as error:
        return {'command': args, 'cwd': str(cwd), 'exit_code': None, 'error': type(error).__name__}


def app_server_probe(root):
    """Handshake and account availability only; never persist account identity/tokens."""
    process = subprocess.Popen(codex_command() + ['app-server'], cwd=root,
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', bufsize=1)
    try:
        rpc = Rpc(process)
        deadline = time.monotonic() + 20
        rpc.request('initialize', {'clientInfo': {'name': 'epicbyte-doctor', 'version': '1.0.0'},
                                  'capabilities': None}, deadline)
        rpc.send({'method': 'initialized', 'params': {}})
        account = rpc.request('account/read', {'refreshToken': False}, deadline)
        return {'initialize': True, 'account_available': account.get('account') is not None,
                'model_turn_executed': False}
    finally:
        stop_process(process)


def doctor(root, probe=False):
    root = Path(root).resolve()
    checks = {'python': sys.version.split()[0], 'git': bool(shutil.which('git')),
              'workspaces': (root / 'workspaces').is_dir(), 'root_writable': os.access(root, os.W_OK),
              'write_isolation': False, 'ready_write': False,
              'write_reason': 'Backend de escrita não certificado; exige testes de confinamento antes de habilitar',
              'provider': 'local Codex App Server; sem fallback de API',
              'environment': {name: os.environ.get(name) for name in
                              ('USERNAME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'HOME', 'CODEX_HOME')},
              'cwd': str(root), 'codex_cmd': shutil.which('codex.cmd' if os.name == 'nt' else 'codex'),
              'actions': []}
    if os.name == 'nt':
        checks['identity'] = command(['whoami', '/user'], root)
        # Read only sandbox selection, never authentication files or full config output.
        config = Path(os.environ.get('CODEX_HOME') or str(Path.home() / '.codex')) / 'config.toml'
        try:
            data = tomllib.loads(config.read_text(encoding='utf-8'))
            checks['windows_sandbox_config'] = data.get('windows', {}).get('sandbox', 'não explícito')
        except (OSError, ValueError):
            checks['windows_sandbox_config'] = 'não legível neste processo'
    try:
        cmd = codex_command()
        checks['launcher'] = cmd
        checks['version'] = command(cmd + ['--version'], root)
        checks['login'] = command(cmd + ['login', 'status'], root)
        checks['codex'] = checks['version']['stdout'] if checks['version']['exit_code'] == 0 else 'indisponível'
        checks['authenticated'] = checks['login']['exit_code'] == 0
    except (RuntimeError, OSError) as error:
        checks.update(codex='indisponível', authenticated=False, launcher_error=str(error))
    if not checks['authenticated']:
        checks['actions'].append('Executar whoami /user e codex login status no terminal local do usuário que já autenticou o ChatGPT. Iniciar a Factory nesse mesmo contexto autorizado. Não copiar auth.json nem mudar USERPROFILE/CODEX_HOME para emprestar credenciais.')
    checks['root_git'] = command(['git', 'rev-parse', '--show-toplevel'], root)
    existing = root / 'workspaces/mission_001'
    if existing.is_dir():
        checks['mission_001_git_probe'] = command(['git', '-C', str(existing), 'status', '--short', '--branch'], root)
        if os.name == 'nt':
            # Static command; no path interpolation into shell code.
            checks['mission_001_owner'] = command([shutil.which('pwsh') or 'powershell.exe', '-NoProfile', '-Command',
                'Get-Acl -LiteralPath workspaces/mission_001,workspaces/mission_001/.git | Format-List Path,Owner'], root)
        head = existing / '.git/HEAD'
        if head.is_file():
            checks['mission_001_head_unverified'] = head.read_text(encoding='utf-8').strip()
        try:
            checks['mission_001_branch'] = validate_git(existing)
        except SafetyError as error:
            # Do not present Git's automatic global safe.directory suggestion as remediation.
            checks['mission_001_git'] = str(error).split('To add an exception')[0].strip()
            checks['actions'].append('Comparar whoami /user com Get-Acl do workspace e .git no host. O responsável deve revisar a origem/propriedade do repositório e executar sob a identidade autorizada ou corrigir ownership/ACL apenas desse workspace. Não adicionar safe.directory global. HEAD lido diretamente não valida a branch.')
    if probe:
        try:
            checks['app_server'] = app_server_probe(root)
        except (RuntimeError, OSError, TimeoutError) as error:
            checks['app_server'] = {'initialize': False, 'error': clean(str(error))}
        if os.name == 'nt' and checks['codex'] != 'indisponível':
            checks['sandbox'] = command(codex_command() + [
                'sandbox', '--include-managed-config', '--permission-profile', ':read-only',
                '-C', str(root), '--', sys.executable, '-c', 'print("EPICBYTE_SANDBOX_OK")'], root)
            checks['sandbox']['command_execution_verified'] = (
                checks['sandbox']['exit_code'] == 0 and checks['sandbox']['stdout'] == 'EPICBYTE_SANDBOX_OK')
            if 'CreateRestrictedToken' in checks['sandbox'].get('stderr', ''):
                checks['sandbox']['probable_cause'] = 'Falha ao criar token restrito; execução já ocorre sob conta sandbox. Sandbox aninhado é uma hipótese, não uma causa confirmada sem teste no host normal.'
        else:
            checks['sandbox'] = {'command_execution_verified': False, 'reason': 'Probe Windows indisponível'}
    checks['actions'].append('No host autorizado, verificar [windows] sandbox no config.toml e reparar o setup pelo Codex se necessário; repetir python factory.py doctor --probe. Não executar outro sandbox dentro de token restrito nem trocar para modo sem isolamento.')
    checks['ready_read_only'] = bool(checks['authenticated'] and checks['codex'] != 'indisponível')
    if probe:
        checks['ready_read_only'] = bool(checks['ready_read_only'] and
            checks['app_server'].get('account_available') and checks['sandbox'].get('command_execution_verified'))
    checks['model_execution_verified'] = False
    checks['sandbox_read_only'] = checks.get('sandbox', {}).get('command_execution_verified', False)
    checks['sandbox_write'] = False
    checks['isolation_certified'] = False
    checks['autonomous_ready'] = False
    if probe:
        from .write_backend import certify
        try:
            certification = certify(root / 'workspaces')
            checks['write_certification'] = certification
            checks['sandbox_write'] = any(c['name'] == 'inside' and c['passed'] for c in certification['checks'])
            checks['isolation_certified'] = certification['certified']
        except (RuntimeError, OSError, TimeoutError, subprocess.TimeoutExpired) as error:
            checks['write_certification'] = {'certified': False, 'error': str(error)}
        checks['write_isolation'] = checks['isolation_certified']
    # Historical mission completion is reported separately from a live sandbox probe.
    db = root / '.factory/factory.sqlite3'
    if db.is_file():
        import sqlite3
        try:
            from contextlib import closing
            with closing(sqlite3.connect('file:' + db.as_posix() + '?mode=ro', uri=True)) as connection:
                row = connection.execute('''SELECT m.id FROM missions m WHERE m.state='COMPLETED'
                    AND EXISTS (SELECT 1 FROM tasks t WHERE t.mission=m.id AND t.state='APPROVED'
                      AND json_extract(t.spec,'$.mode')='write'
                      AND 4=(SELECT count(DISTINCT e.role) FROM evidence e JOIN executions x ON x.id=e.execution
                        WHERE e.mission=t.mission AND e.task=t.id AND e.attempt=t.attempts
                        AND e.role IN ('developer','code_reviewer','security_reviewer','qa')
                        AND x.status='COMPLETED' AND json_extract(x.report,'$.provider')='codex-app-server'))
                    ORDER BY m.created DESC LIMIT 1''').fetchone()
                checks['verified_write_mission'] = row[0] if row else None
                checks['model_execution_verified'] = row is not None
        except sqlite3.Error:
            checks['verified_write_mission'] = None
    checks['ready_write'] = bool(checks['ready_read_only'] and checks['isolation_certified'] and checks['model_execution_verified'])
    checks['autonomous_ready'] = checks['ready_write']
    checks['write_reason'] = 'Exige probe atual de isolamento e missão de escrita COMPLETED com evidências independentes'
    return checks
