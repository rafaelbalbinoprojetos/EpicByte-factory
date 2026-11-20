import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from epicbyte.safety import GIT
from epicbyte.safety import SafetyError, relative_file, snapshot, IsolationPolicy
from epicbyte.write_backend import validate_edits, apply_edits, certify, sandbox_command


class WriteBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def test_valid_create_and_replace(self):
        edits = [{'path': 'src/a.py', 'content': 'print(1)'}]
        self.assertEqual(validate_edits(self.workspace, edits), edits)
        (self.workspace / 'a.py').write_text('old')
        self.assertEqual(len(validate_edits(self.workspace, [{'path':'a.py','content':'new'}])), 1)

    def test_external_paths_rejected(self):
        for name in ('../outside', str(self.root / 'outside'), 'C:/outside', '//server/share/a', 'a/../../x'):
            with self.subTest(name=name), self.assertRaises(SafetyError):
                validate_edits(self.workspace, [{'path': name, 'content': 'x'}])

    def test_protected_case_and_windows_aliases(self):
        for name in ('.GIT/config', '.AWS/x', 'a./x', 'a /x', '.Codex/x', 'x:ads'):
            with self.subTest(name=name), self.assertRaises(SafetyError):
                relative_file(self.workspace, name)

    def test_destructive_operations_rejected(self):
        for edits in ([{'path':'a','delete':True}], [{'command':'rm -rf .'}], [{'path':'a','content':'x','operation':'delete'}], []):
            with self.subTest(edits=edits), self.assertRaises(SafetyError):
                validate_edits(self.workspace, edits)

    def test_duplicate_and_oversized_rejected(self):
        for edits in ([{'path':'a','content':'x'},{'path':'A','content':'x'}], [{'path':'a','content':'x'*1000001}]):
            with self.assertRaises(SafetyError): validate_edits(self.workspace, edits)

    def test_hardlinks_rejected(self):
        source = self.root / 'external'
        source.write_text('sentinel')
        (self.workspace / 'linked').hardlink_to(source)
        with self.assertRaises(SafetyError): snapshot(self.workspace)
        self.assertEqual(source.read_text(), 'sentinel')

    def test_link_resolution_blocks_escape(self):
        # Use a deterministic junction on Windows, symlink elsewhere.
        import os, subprocess
        outside = self.root / 'outside'; outside.mkdir()
        link = self.workspace / 'link'
        try:
            if os.name == 'nt':
                result = subprocess.run(['cmd','/c','mklink','/J',str(link),str(outside)], capture_output=True)
                self.assertEqual(result.returncode, 0)
            else: link.symlink_to(outside, target_is_directory=True)
            with self.assertRaises(SafetyError): relative_file(self.workspace, 'link/escape')
            with self.assertRaises(SafetyError): snapshot(self.workspace)
        finally:
            if link.is_symlink(): link.unlink()
            elif link.exists(): link.rmdir()

    def test_uncertified_writer_never_launches(self):
        with patch('epicbyte.safety.validate_git'), patch('epicbyte.write_backend.certify', return_value={'certified':False}), patch('epicbyte.write_backend.subprocess.run') as run:
            with self.assertRaises(SafetyError): IsolationPolicy().require_write(self.workspace)
            run.assert_not_called()

    def test_main_block_before_writer(self):
        with patch('epicbyte.write_backend.validate_git', side_effect=SafetyError('main')), patch('epicbyte.write_backend.subprocess.run') as run:
            with self.assertRaises(SafetyError): apply_edits(self.workspace, [{'path':'a','content':'x'}])
            run.assert_not_called()

    def test_failed_sandbox_is_not_denial_evidence(self):
        from subprocess import CompletedProcess
        with patch('epicbyte.write_backend.sandbox_run', return_value=CompletedProcess([],1,'','CreateRestrictedToken failed: 87')):
            report = certify(self.root)
        self.assertFalse(report['certified'])
        self.assertEqual(len(report['checks']), 1)

    def test_certification_unlocks_only_valid_workspace(self):
        with patch('epicbyte.safety.validate_git'), patch('epicbyte.write_backend.certify', return_value={'certified': True}) as certify_mock:
            IsolationPolicy().require_write(self.workspace)
            certify_mock.assert_called_once_with(self.workspace.parent)

    def test_provider_applies_structured_edits_after_readonly_turn(self):
        from epicbyte.provider import CodexProvider, Result
        from unittest.mock import Mock
        process, rpc = Mock(), Mock()
        rpc.request.side_effect = [{}, {'thread': {'id':'t'}}, {'turn': {'id':'u'}}]
        with patch('epicbyte.safety.IsolationPolicy.require_write'), patch('epicbyte.provider.codex_command', return_value=['codex']), patch('epicbyte.provider.subprocess.Popen', return_value=process), patch('epicbyte.provider.Rpc', return_value=rpc), patch('epicbyte.provider.stop_process'), patch('epicbyte.provider.collect_turn', return_value=Result('{"edits":[{"path":"a","content":"x"}]}','t','u')), patch('epicbyte.write_backend.apply_edits', return_value=['a']) as apply:
            result = CodexProvider().execute('task', self.workspace, write=True)
        self.assertEqual(result.provider, 'codex-app-server')
        self.assertEqual(json.loads(result.text)['files'], ['a'])
        apply.assert_called_once_with(self.workspace, [{'path':'a','content':'x'}])
        self.assertEqual(rpc.request.call_args_list[1].args[1]['sandbox'], 'read-only')

    def test_real_main_repository_rejected(self):
        import subprocess
        from epicbyte.safety import validate_git
        subprocess.run([GIT,'init','-b','main',str(self.workspace)], check=True, capture_output=True)
        with self.assertRaises(SafetyError): validate_git(self.workspace)

    def test_timeout_stops_sandbox_tree(self):
        from epicbyte.write_backend import sandbox_run
        from unittest.mock import Mock
        import subprocess
        process = Mock()
        process.communicate.side_effect = subprocess.TimeoutExpired('codex', 1)
        with patch('epicbyte.write_backend.subprocess.Popen', return_value=process), patch('epicbyte.write_backend.sandbox_command', return_value=['codex']), patch('epicbyte.write_backend.stop_process') as stop:
            with self.assertRaises(subprocess.TimeoutExpired): sandbox_run(self.workspace, 'pass', timeout=1)
            stop.assert_called_once_with(process)

    def test_profile_is_explicit_no_temp_or_extra_roots(self):
        with patch('epicbyte.write_backend.codex_command', return_value=['codex']):
            command = sandbox_command(self.workspace, 'print(1)')
        self.assertIn('--include-managed-config', command)
        self.assertIn('epicbyte', command)
        self.assertNotIn(':workspace', command)
        self.assertIn('network={enabled=false}', command[2])

    def test_failed_write_raises(self):
        from subprocess import CompletedProcess
        with patch('epicbyte.write_backend.validate_git'), patch('epicbyte.safety.IsolationPolicy.require_write'), patch('epicbyte.write_backend.sandbox_run', return_value=CompletedProcess([],1,'','sandbox offline')):
            with self.assertRaises(SafetyError): apply_edits(self.workspace,[{'path':'a','content':'x'}])


if __name__ == '__main__': unittest.main()
