import hashlib
import os
import subprocess
from pathlib import Path, PureWindowsPath


def find_git():
    """Git do PATH ou da instalação padrão do Windows (o PowerShell nem sempre herda o PATH do Git)."""
    import shutil
    found = shutil.which('git')
    if found:
        return found
    for base in (os.environ.get('ProgramFiles', r'C:\Program Files'), os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs')):
        candidate = Path(base) / 'Git' / 'cmd' / 'git.exe'
        if candidate.is_file():
            return str(candidate)
    return 'git'


GIT = find_git()


class SafetyError(RuntimeError):
    pass


# Gerados por ferramentas (instalação, build, testes): fora da impressão digital do workspace.
GENERATED_DIRS = {'.git', '__pycache__', 'node_modules', 'dist', 'coverage', '.vite', 'test-results', 'playwright-report'}
GENERATED_SUFFIXES = ('.tsbuildinfo',)
# Só o motor mexe em dependências (a partir do template); o agente não troca pacote nem scripts das verificações.
LOCKED_FILES = {'package.json', 'package-lock.json', '.npmrc', 'npm-shrinkwrap.json'}


def within(root, path):
    root, path = Path(root).resolve(), Path(path).resolve()
    if not path.is_relative_to(root) or path == root:
        raise SafetyError('Caminho fora da raiz autorizada')
    return path


def relative_file(root, name):
    if not isinstance(name, str) or not name or '\\' in name or ':' in name or PureWindowsPath(name).is_absolute():
        raise SafetyError('Nome de arquivo inválido')
    parts = Path(name).parts
    if any(p.casefold() in ('.git', '.codex', '.agents', '.aws', '..') or p.endswith((' ', '.')) or p.upper().split('.')[0] in ('CON', 'NUL', 'PRN', 'AUX', 'COM1', 'LPT1') for p in parts):
        raise SafetyError('Caminho protegido')
    if any(p.casefold() in GENERATED_DIRS for p in parts[:-1]) or parts[-1].casefold() in LOCKED_FILES:
        raise SafetyError('Arquivo gerado ou de dependências: só o motor altera')
    return within(root, Path(root) / name)


def git(workspace, *args):
    result = subprocess.run([GIT, '-C', str(workspace), *args], capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise SafetyError('Git não validado: ' + result.stderr.strip())
    return result.stdout.strip()


def validate_git(workspace):
    for path in (Path(workspace), Path(workspace) / '.git'):
        if path.is_symlink() or getattr(path, 'is_junction', lambda: False)():
            raise SafetyError('Raiz ou metadados Git redirecionados')
    if Path(git(workspace, 'rev-parse', '--show-toplevel')).resolve() != Path(workspace).resolve():
        raise SafetyError('Workspace deve ser a raiz Git')
    branch = git(workspace, 'branch', '--show-current')
    if branch != 'develop':
        raise SafetyError('Escrita permitida somente na branch develop; atual: ' + branch)
    return branch


def snapshot(root):
    result = {}
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if d not in GENERATED_DIRS]
        for directory in dirs:
            p = Path(base) / directory
            if p.is_symlink() or (hasattr(p, 'is_junction') and p.is_junction()):
                raise SafetyError('Link/junction no workspace')
        for name in files:
            if name.endswith(GENERATED_SUFFIXES):
                continue
            original = Path(base) / name
            if original.stat().st_nlink != 1:
                raise SafetyError('Hardlink no workspace')
            if original.is_symlink():
                raise SafetyError('Link no workspace')
            path = within(root, original)
            result[path.relative_to(root).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


class IsolationPolicy:
    """Fail closed. Native sandbox presence alone is not an isolation attestation."""
    def require_write(self, workspace):
        validate_git(workspace)
        snapshot(workspace)
        from .write_backend import certify
        result = certify(Path(workspace).parent)
        if not result['certified']:
            raise SafetyError('Escrita bloqueada: sandbox sem certificacao: ' + str(result))
