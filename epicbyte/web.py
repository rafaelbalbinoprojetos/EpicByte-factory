"""Projetos web: template, instalação controlada, verificações no sandbox, commits e pré-visualização.

Regras de segurança:
- Dependências vêm só do template (package.json/package-lock.json travados para os agentes).
- `npm ci --ignore-scripts` roda no motor, com rede, sem executar scripts de instalação.
- Todo código escrito pelos agentes (typecheck, lint, testes, build) roda no sandbox do Codex, sem rede.
- A pré-visualização só serve arquivos estáticos de dist/ (nada é executado no servidor).
"""
import functools
import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .safety import GIT, GENERATED_DIRS, SafetyError

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / 'templates'
AVAILABLE = {'web-react': 'Site / landing page (React + TypeScript + Tailwind)'}
GATES = ('typecheck', 'lint', 'test', 'build')
NPM = 'npm.cmd' if os.name == 'nt' else 'npm'
GIT_ID = ['-c', 'user.name=EpicByte Factory', '-c', 'user.email=factory@epicbyte.local']


def is_web(workspace):
    return (Path(workspace) / 'package.json').is_file()


def _git(workspace, *args):
    return subprocess.run([GIT, '-C', str(workspace), *GIT_ID, *args], capture_output=True, text=True, timeout=60)


def prepare_workspace(workspace, template):
    """Copia o template, faz o commit inicial na develop e instala as dependências travadas."""
    if template not in AVAILABLE:
        raise SafetyError('Template desconhecido')
    source = TEMPLATES / template
    if not (source / 'package-lock.json').is_file():
        raise SafetyError('Template sem package-lock.json')
    shutil.copytree(source, workspace, dirs_exist_ok=True, ignore=shutil.ignore_patterns(*GENERATED_DIRS, '*.tsbuildinfo'))
    _git(workspace, 'add', '-A')
    _git(workspace, 'commit', '-m', f'Template {template}')
    install(workspace)


def install(workspace):
    result = subprocess.run([NPM, 'ci', '--ignore-scripts', '--no-audit', '--no-fund', '--cache', str(ROOT / '.npm-cache')],
                            cwd=workspace, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900)
    if result.returncode:
        raise SafetyError('npm ci falhou: ' + (result.stderr or result.stdout)[-1500:])


def _tail(text, lines=40):
    return '\n'.join((text or '').strip().splitlines()[-lines:])


def run_gates(workspace, timeout=300):
    """Executa as verificações do projeto no sandbox (sem rede) e devolve as evidências."""
    from .write_backend import sandbox_exec
    results = []
    for script in GATES:
        started = time.monotonic()
        try:
            proc = sandbox_exec(workspace, ['cmd', '/c', f'npm run {script}'] if os.name == 'nt' else ['npm', 'run', script], timeout=timeout)
            code, output = proc.returncode, (proc.stdout or '') + (proc.stderr or '')
        except subprocess.TimeoutExpired:
            code, output = -1, f'Tempo esgotado ({timeout}s)'
        results.append({'gate': script, 'exit_code': code, 'passed': code == 0,
                        'duration': round(time.monotonic() - started, 1), 'output': _tail(output)})
    results.append(audit(workspace))
    return {'passed': all(r['passed'] for r in results), 'results': results}


def audit(workspace):
    """npm audit lê só o lockfile (não executa código do projeto); falha em vulnerabilidade alta ou crítica."""
    started = time.monotonic()
    proc = subprocess.run([NPM, 'audit', '--omit=dev', '--json'], cwd=workspace, capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=120)
    try:
        counts = json.loads(proc.stdout or '{}').get('metadata', {}).get('vulnerabilities', {})
    except json.JSONDecodeError:
        counts = {}
    blocking = int(counts.get('high', 0)) + int(counts.get('critical', 0))
    reachable = bool(counts) or proc.returncode == 0
    return {'gate': 'audit', 'exit_code': proc.returncode, 'passed': reachable and blocking == 0,
            'duration': round(time.monotonic() - started, 1),
            'output': json.dumps(counts) if counts else _tail(proc.stderr or proc.stdout, 10)}


ASSET_TYPES = {'.png', '.jpg', '.jpeg', '.webp', '.avif'}   # só raster: SVG pode carregar script
ASSET_MAX = 15 * 1024 * 1024


def slug(name):
    import re
    import unicodedata
    stem, suffix = Path(name).stem, Path(name).suffix.lower()
    stem = unicodedata.normalize('NFKD', stem).encode('ascii', 'ignore').decode()
    return (re.sub(r'[^a-z0-9]+', '-', stem.lower()).strip('-') or 'imagem') + suffix


def available_assets(root=ROOT):
    folder = Path(root) / 'images'
    if not folder.is_dir():
        return []
    return sorted(p.name for p in folder.iterdir() if p.is_file() and p.suffix.lower() in ASSET_TYPES and p.stat().st_size <= ASSET_MAX)


def copy_assets(workspace, names, root=ROOT):
    """Copia imagens escolhidas de images/ para public/assets/ e devolve os caminhos usados no site."""
    folder = (Path(root) / 'images').resolve()
    allowed = set(available_assets(root))
    target = Path(workspace) / 'public' / 'assets'
    target.mkdir(parents=True, exist_ok=True)
    used = []
    for name in names:
        if name not in allowed:
            raise SafetyError('Imagem não permitida: ' + str(name)[:80])
        source = (folder / name).resolve()
        if source.parent != folder:
            raise SafetyError('Imagem fora da pasta images/')
        dest = target / slug(name)
        shutil.copyfile(source, dest)
        item = {'original': name, 'path': './assets/' + dest.name}
        try:   # versão otimizada para a web (mantém transparência), com largura máxima de 1600px
            from PIL import Image
            with Image.open(source) as image:
                item['width'], item['height'] = image.size
                if dest.suffix != '.webp':
                    image.thumbnail((1600, 1600))
                    optimized = dest.with_suffix('.webp')
                    image.save(optimized, 'WEBP', quality=85, method=6)
                    item['webp'] = './assets/' + optimized.name
                    item['webp_size'] = list(image.size)
        except Exception:
            pass
        used.append(item)
    return used


def commit_task(workspace, message):
    """Commit do trabalho aprovado (somente na develop; arquivos gerados ficam fora pelo .gitignore)."""
    if _git(workspace, 'branch', '--show-current').stdout.strip() != 'develop':
        raise SafetyError('Commit permitido somente na develop')
    _git(workspace, 'add', '-A')
    if not _git(workspace, 'status', '--porcelain').stdout.strip():
        return None
    result = _git(workspace, 'commit', '-m', message[:200])
    if result.returncode:
        raise SafetyError('Commit falhou: ' + result.stderr.strip()[-500:])
    return _git(workspace, 'rev-parse', '--short', 'HEAD').stdout.strip()


# ── Pré-visualização: servidor estático por missão em 127.0.0.1 ──
_previews = {}
_preview_lock = threading.Lock()


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def preview_port(mission):
    return 5900 + int(hashlib.sha256(mission.encode()).hexdigest(), 16) % 100


def start_preview(mission, workspace):
    dist = Path(workspace) / 'dist'
    if not (dist / 'index.html').is_file():
        raise SafetyError('Ainda não há build: as verificações precisam passar ao menos uma vez')
    with _preview_lock:
        current = _previews.get(mission)
        if current:
            return current[1]
        port = preview_port(mission)
        for candidate in [port, *range(5900, 6000)]:
            try:
                server = ThreadingHTTPServer(('127.0.0.1', candidate), functools.partial(_Quiet, directory=str(dist)))
                break
            except OSError:
                continue
        else:
            raise SafetyError('Nenhuma porta livre entre 5900 e 5999')
        threading.Thread(target=server.serve_forever, daemon=True).start()
        url = f'http://127.0.0.1:{server.server_address[1]}/'
        _previews[mission] = (server, url)
        return url
