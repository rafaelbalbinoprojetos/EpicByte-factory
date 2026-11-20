import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from epicbyte import web
from epicbyte.safety import GIT, SafetyError, relative_file, snapshot


class SafetyForWebTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.root = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def test_agents_cannot_touch_dependencies_or_generated_files(self):
        for name in ('package.json', 'package-lock.json', '.npmrc', 'node_modules/x/index.js', 'dist/index.html', 'sub/node_modules/a.js'):
            with self.assertRaises(SafetyError, msg=name):
                relative_file(self.root, name, write=True)
            relative_file(self.root, name)   # ler/citar como evidência continua permitido
        self.assertTrue(str(relative_file(self.root, 'src/App.tsx')).endswith('App.tsx'))

    def test_snapshot_ignores_generated_folders(self):
        (self.root / 'src').mkdir()
        (self.root / 'src' / 'App.tsx').write_text('x', encoding='utf-8')
        for folder in ('node_modules/pkg', 'dist/assets', 'coverage'):
            (self.root / folder).mkdir(parents=True)
            (self.root / folder / 'f.js').write_text('y', encoding='utf-8')
        (self.root / 'tsconfig.tsbuildinfo').write_text('z', encoding='utf-8')
        self.assertEqual(list(snapshot(self.root)), ['src/App.tsx'])


class CommitTests(unittest.TestCase):
    def test_commits_only_on_develop_and_skips_when_clean(self):
        with tempfile.TemporaryDirectory() as d:
            subprocess.run([GIT, 'init', '-b', 'develop', d], check=True, capture_output=True)
            Path(d, '.gitignore').write_text('node_modules/\n', encoding='utf-8')
            Path(d, 'a.txt').write_text('1', encoding='utf-8')
            Path(d, 'node_modules').mkdir()
            Path(d, 'node_modules', 'big.js').write_text('2', encoding='utf-8')
            self.assertTrue(web.commit_task(d, 'TASK-001: primeira'))
            tracked = subprocess.run([GIT, '-C', d, 'ls-files'], capture_output=True, text=True).stdout.split()
            self.assertEqual(sorted(tracked), ['.gitignore', 'a.txt'])
            self.assertIsNone(web.commit_task(d, 'TASK-002: nada mudou'))
            subprocess.run([GIT, '-C', d, 'checkout', '-q', '-b', 'main'], check=True)
            Path(d, 'b.txt').write_text('3', encoding='utf-8')
            with self.assertRaises(SafetyError):
                web.commit_task(d, 'TASK-003: na main')


class GatesTests(unittest.TestCase):
    def test_all_gates_must_pass(self):
        ok = subprocess.CompletedProcess([], 0, 'ok', '')
        bad = subprocess.CompletedProcess([], 2, '', 'erro de tipo')
        audit_ok = {'gate': 'audit', 'exit_code': 0, 'passed': True, 'duration': 0, 'output': '{}'}
        with patch('epicbyte.write_backend.sandbox_exec', side_effect=[ok, bad, ok, ok]), patch.object(web, 'audit', return_value=audit_ok):
            result = web.run_gates('.')
        self.assertFalse(result['passed'])
        self.assertEqual([g['gate'] for g in result['results'] if not g['passed']], ['lint'])
        with patch('epicbyte.write_backend.sandbox_exec', return_value=ok), patch.object(web, 'audit', return_value=audit_ok):
            self.assertTrue(web.run_gates('.')['passed'])

    def test_unknown_template_rejected(self):
        with tempfile.TemporaryDirectory() as d, self.assertRaises(SafetyError):
            web.prepare_workspace(d, '../fora')


if __name__ == '__main__':
    unittest.main()


class ReopenTests(unittest.TestCase):
    def test_reopen_resets_blocked_tasks_only(self):
        import json
        from epicbyte.storage import Store
        with tempfile.TemporaryDirectory() as d:
            store = Store(str(Path(d) / 'db.sqlite3'))
            store.create('m', '# missão', d)
            spec = lambda i, deps: {'id': i, 'agent': 'developer', 'mode': 'write', 'description': i, 'acceptance_criteria': ['ok'], 'dependencies': deps}
            store.save_plan('m', {'tasks': [spec('T1', []), spec('T2', ['T1'])]})
            for target in ('PLANNING', 'RUNNING', 'BLOCKED'):
                store.transition('m', target)
            store.transition('m', 'BLOCKED', 'T1')
            store.transition('m', 'BLOCKED', 'T2')
            with store.db:
                store.db.execute("UPDATE tasks SET attempts=4, fixes=3 WHERE mission='m'")
            self.assertEqual(sorted(store.reopen_blocked('m')), ['T1', 'T2'])
            rows = {t['id']: (t['state'], t['attempts'], t['fixes']) for t in store.tasks('m')}
            self.assertEqual(rows, {'T1': ('PENDING', 0, 0), 'T2': ('PENDING', 0, 0)})
            self.assertTrue(store.db.execute("SELECT 1 FROM events WHERE type='TASKS_REOPENED'").fetchone())
            store.db.close()


class SecurityApprovalTests(unittest.TestCase):
    def test_security_uses_its_own_criteria(self):
        from epicbyte.engine import security_approved
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'App.tsx').write_text('x', encoding='utf-8')
            ok = {'verdict': 'APPROVED', 'criteria': [{'index': i, 'status': 'APPROVED', 'evidence': 'ok', 'files': ['App.tsx']} for i in range(5)]}
            self.assertTrue(security_approved(ok, d))
            self.assertFalse(security_approved({**ok, 'verdict': 'REJECTED'}, d))
            self.assertFalse(security_approved({'verdict': 'APPROVED', 'criteria': []}, d))
            bad = {'verdict': 'APPROVED', 'criteria': [{'index': 0, 'status': 'REJECTED', 'evidence': 'x'}]}
            self.assertFalse(security_approved(bad, d))
            self.assertFalse(security_approved({'verdict': 'APPROVED', 'criteria': [{'index': 0, 'status': 'APPROVED', 'evidence': ''}]}, d))


class EvidencePathTests(unittest.TestCase):
    def test_folder_cited_as_evidence_is_accepted_but_missing_path_is_not(self):
        from epicbyte.engine import audit_approved
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'src', 'sections').mkdir(parents=True)
            Path(d, 'src', 'App.tsx').write_text('x', encoding='utf-8')
            spec = {'acceptance_criteria': ['a', 'b']}
            report = lambda files: {'verdict': 'APPROVED', 'criteria': [{'index': i, 'status': 'APPROVED', 'evidence': 'ok', 'files': files} for i in range(2)]}
            self.assertTrue(audit_approved(report(['src/sections', 'src/App.tsx']), spec, d))
            self.assertFalse(audit_approved(report(['src/nao-existe.tsx']), spec, d))
