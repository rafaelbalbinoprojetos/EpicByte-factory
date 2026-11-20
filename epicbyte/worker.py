import sys
from pathlib import Path
from .storage import Store
from .engine import WorkflowEngine, limits_for
from .provider import CodexProvider

store = Store(sys.argv[1])
try:
    WorkflowEngine(store,CodexProvider(),Path(__file__).resolve().parents[1]/'agents',limits=limits_for(store,sys.argv[2])).run(sys.argv[2])
finally:
    store.db.close()
