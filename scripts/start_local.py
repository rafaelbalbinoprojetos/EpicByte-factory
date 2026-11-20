"""Build and serve the local dashboard. Ctrl+C shuts down backend workers."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
sys.path.insert(0,str(ROOT))
import epicbyte  # noqa: E402  coloca Python, Git, Node e Codex no PATH antes do npm
npm = 'npm.cmd' if os.name == 'nt' else 'npm'
if not (ROOT/'frontend/node_modules').is_dir():
    subprocess.run([npm,'ci','--cache',str(ROOT/'.npm-cache')],cwd=ROOT/'frontend',check=True)
subprocess.run([npm,'run','build'],cwd=ROOT/'frontend',check=True)
sys.path.insert(0,str(ROOT))
from epicbyte.cli import main
raise SystemExit(main(['serve']))
