"""Structured Developer edits; the only writer runs inside the official sandbox."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from .provider import codex_command, stop_process
from .safety import SafetyError, relative_file, snapshot, validate_git


def sandbox_command(workspace, code, *args):
    # Per-process configuration only. No inherited workspace or temporary write grants.
    profile = '{filesystem={":root"="read",":workspace_roots"={"."="write",".git"="read",".codex"="read",".agents"="read",".aws"="read"}},network={enabled=false}}'
    return codex_command() + ['-c', 'permissions.epicbyte=' + profile,
        'sandbox', '--include-managed-config', '-P', 'epicbyte', '-C', str(workspace),
        '--', sys.executable, '-I', '-B', '-c', code, *args]


def sandbox_run(workspace, code, *args, timeout=30, input=None):
    process = subprocess.Popen(sandbox_command(workspace, code, *args), cwd=workspace,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding='utf-8', errors='replace')
    try:
        stdout, stderr = process.communicate(input=input, timeout=timeout)
        return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
    finally:
        stop_process(process)


def certify(parent):
    """Never trust a persisted flag. Exercise the current launcher/token/config."""
    evidence = []
    with tempfile.TemporaryDirectory(prefix='epicbyte-cert-', dir=parent) as directory:
        base = Path(directory)
        workspace, outside = base / 'workspace', base / 'outside'
        workspace.mkdir(); outside.mkdir()
        code = '''import pathlib,sys
p=pathlib.Path(sys.argv[1])
try:
 p.write_text("probe",encoding="utf-8")
except PermissionError:
 print("DENIED")
else:
 print("WRITTEN")
'''
        def probe(name, target, expected):
            result = sandbox_run(workspace, code, str(target))
            ok = result.returncode == 0 and result.stdout.strip() == expected
            evidence.append(dict(name=name, passed=ok, exit_code=result.returncode,
                                 stdout=result.stdout.strip(), stderr=result.stderr.strip()))
            return ok
        if not probe('inside', workspace / 'allowed.txt', 'WRITTEN'):
            return {'certified': False, 'checks': evidence}
        targets = [('absolute', outside / 'absolute.txt'), ('relative', Path('../outside/relative.txt')),
                   ('system_temp', Path(tempfile.gettempdir()) / (base.name + '.txt'))]
        # External probes are exclusively fresh disposable targets, never user files.
        for name, target in targets:
            probe(name, target, 'DENIED')
            actual = (workspace / target).resolve() if not target.is_absolute() else target
            if actual.exists():
                actual.unlink()
        for kind in ('symlink', 'junction') if os.name == 'nt' else ('symlink',):
            link = workspace / kind
            try:
                if kind == 'junction':
                    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
                    if result.returncode: raise OSError('junction unavailable')
                else:
                    link.symlink_to(outside, target_is_directory=True)
                probe(kind, link / (kind + '.txt'), 'DENIED')
            except OSError as error:
                evidence.append({'name': kind, 'passed': False, 'error': str(error)})
            finally:
                if link.is_symlink(): link.unlink()
                elif link.exists() and getattr(link, 'is_junction', lambda: False)(): link.rmdir()
        return {'certified': all(e['passed'] for e in evidence), 'checks': evidence}


def validate_edits(workspace, edits):
    snapshot(workspace)
    if not isinstance(edits, list) or not edits or len(edits) > 100:
        raise SafetyError('Developer deve fornecer 1..100 edições')
    names = set()
    for edit in edits:
        if not isinstance(edit, dict) or set(edit) != {'path', 'content'}:
            raise SafetyError('Somente criação/substituição de conteúdo; exclusão e comandos recusados')
        path = relative_file(workspace, edit['path'], write=True)
        key = str(path).casefold()
        if key in names or not isinstance(edit['content'], str) or len(edit['content'].encode()) > 1000000:
            raise SafetyError('Edição inválida ou duplicada')
        names.add(key)
    return edits


def apply_edits(workspace, edits):
    validate_git(workspace)
    validate_edits(workspace, edits)
    from .safety import IsolationPolicy
    IsolationPolicy().require_write(workspace)
    # Input arrives via stdin, not executable shell interpolation or argv size limits.
    code = '''import json,pathlib,sys,os
root=pathlib.Path.cwd().resolve()
for edit in json.loads(sys.stdin.read()):
 p=(root/edit['path']).resolve()
 if not p.is_relative_to(root) or p==root: raise RuntimeError("escape")
 p.parent.mkdir(parents=True,exist_ok=True)
 tmp=p.with_name(p.name+".epicbyte-pending")
 with tmp.open("x",encoding="utf-8",newline="") as f:
  f.write(edit['content']);f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
print("APPLIED")
'''
    result = sandbox_run(workspace, code, input=json.dumps(edits))
    if result.returncode or result.stdout.strip() != 'APPLIED':
        raise SafetyError('Writer sandbox falhou: ' + result.stderr.strip())
    return [e['path'] for e in edits]


def sandbox_exec(workspace, argv, timeout=300):
    """Executa um comando do projeto no sandbox oficial: escrita só no workspace, sem rede."""
    profile = '{filesystem={":root"="read",":workspace_roots"={"."="write",".git"="read",".codex"="read",".agents"="read",".aws"="read"}},network={enabled=false}}'
    command = codex_command() + ['-c', 'permissions.epicbyte=' + profile, 'sandbox', '--include-managed-config',
                                 '-P', 'epicbyte', '-C', str(workspace), '--', *argv]
    process = subprocess.Popen(command, cwd=workspace, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, encoding='utf-8', errors='replace')
    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return subprocess.CompletedProcess(process.args, process.returncode, stdout, stderr)
    finally:
        stop_process(process)
