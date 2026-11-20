"""EpicByte Factory local orchestration core."""
import os
import shutil
import sys
from pathlib import Path

__version__ = "1.0.0"


def _tool_dirs():
    """Pastas das ferramentas que a fábrica usa (Python, Git, Node, Codex).

    Os agentes e o QA rodam no sandbox do Codex herdando o PATH deste processo; quando o
    servidor é aberto de um terminal sem essas pastas, o QA não acha `python` e reprova
    tarefas corretas por falta de ambiente."""
    program_files = Path(os.environ.get('ProgramFiles', r'C:\Program Files'))
    candidates = [
        Path(sys.executable).parent,
        Path(sys.executable).parent / 'Scripts',
        program_files / 'Git' / 'cmd',
        program_files / 'nodejs',
        Path(os.environ.get('APPDATA', '')) / 'npm',
    ]
    for name in ('git', 'node', 'codex'):
        found = shutil.which(name)
        if found:
            candidates.append(Path(found).parent)
    return [str(p) for p in candidates if str(p) and p.is_dir()]


def ensure_tool_path():
    current = os.environ.get('PATH', '').split(os.pathsep)
    known = {os.path.normcase(p.rstrip('\\/')) for p in current if p}
    extra = []
    for d in _tool_dirs():
        key = os.path.normcase(d.rstrip('\\/'))
        if key not in known:
            known.add(key)
            extra.append(d)
    if extra:
        os.environ['PATH'] = os.pathsep.join(extra + current)
    return extra


ensure_tool_path()
