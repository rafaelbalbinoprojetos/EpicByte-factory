"""Run on the authenticated host. No model calls before live certification succeeds."""
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from epicbyte.write_backend import certify
from epicbyte.diagnostics import doctor
from epicbyte.cli import create_mission, status
from epicbyte.storage import Store
from epicbyte.engine import WorkflowEngine
from epicbyte.provider import CodexProvider


def run():
    report = {'certification': None, 'mission_exit_code': None, 'ready_write': False, 'developer_files': [], 'qa_commands': []}
    target = ROOT / 'logs/write_host_validation.json'
    target.parent.mkdir(exist_ok=True)
    try:
        tests = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'], cwd=ROOT, capture_output=True, text=True)
        report['tests'] = {'exit_code': tests.returncode, 'output': tests.stdout + tests.stderr}
        if tests.returncode:
            return 2
        report['certification'] = certify(ROOT / 'workspaces')
        if not report['certification']['certified']:
            return 2
        store = Store(ROOT / '.factory/factory.sqlite3')
        try:
            plan = json.loads((ROOT / 'missions/write_smoke_plan.json').read_text(encoding='utf-8-sig'))
            ident = create_mission(store, ROOT, 'missions/write_smoke.md', plan)
            report['mission_id'] = ident
            WorkflowEngine(store, CodexProvider(), ROOT / 'agents').run(ident)
            report['mission'] = status(store, ident)
            report['mission_exit_code'] = 0 if report['mission']['state'] == 'COMPLETED' else 2
            report['developer_files'] = []
            report['qa_commands'] = []
            for row in store.db.execute('SELECT agent,report FROM executions WHERE mission=? AND status=? ORDER BY id', (ident, 'COMPLETED')):
                execution = json.loads(row['report'])
                if row['agent'] == 'developer': report['developer_files'].extend(execution['report'].get('files', []))
                if row['agent'] == 'qa': report['qa_commands'].extend(execution.get('commands', []))
        finally:
            store.db.close()
        report['doctor'] = doctor(ROOT, probe=True)
        report['ready_write'] = report['mission_exit_code'] == 0 and report['doctor']['ready_write']
        return 0 if report['ready_write'] else 2
    except Exception as error:
        report['error'] = str(error)
        return 2
    finally:
        target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    raise SystemExit(run())
