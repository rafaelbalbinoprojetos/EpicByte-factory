import io
import tempfile
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from epicbyte.cli import ROOT, main
from epicbyte.diagnostics import app_server_probe, doctor
from epicbyte.provider import codex_command


class DiagnosticsTests(unittest.TestCase):
    def test_windows_launcher_preserves_node_wrapper_even_when_binary_exists(self):
        with patch('epicbyte.provider.os.name', 'nt'), \
             patch('epicbyte.provider.shutil.which', side_effect=['C:/npm/codex.cmd', 'C:/node.exe']), \
             patch('pathlib.Path.is_file', side_effect=[False, True]):
            self.assertEqual(codex_command(), ['C:/node.exe', str(Path('C:/npm/node_modules/@openai/codex/bin/codex.js'))])

    def test_missing_install_fails_closed(self):
        with patch('epicbyte.provider.shutil.which', return_value=None):
            with self.assertRaisesRegex(RuntimeError, 'indisponível'):
                codex_command()

    def test_account_probe_does_not_return_identity(self):
        process, rpc = Mock(), Mock()
        rpc.request.side_effect = [{}, {'account': {'email': 'private@example.test', 'token': 'secret'}}]
        with patch('epicbyte.diagnostics.subprocess.Popen', return_value=process), \
             patch('epicbyte.diagnostics.codex_command', return_value=['codex']), \
             patch('epicbyte.diagnostics.Rpc', return_value=rpc), \
             patch('epicbyte.diagnostics.stop_process') as stop:
            result = app_server_probe(ROOT)
        self.assertEqual(result, {'initialize': True, 'account_available': True, 'model_turn_executed': False})
        stop.assert_called_once_with(process)
        self.assertEqual(rpc.request.call_args.args[:2], ('account/read', {'refreshToken': False}))

    def test_probe_timeout_closes_process(self):
        with patch('epicbyte.diagnostics.subprocess.Popen') as process, \
             patch('epicbyte.diagnostics.codex_command', return_value=['codex']), \
             patch('epicbyte.diagnostics.Rpc') as rpc, \
             patch('epicbyte.diagnostics.stop_process') as stop:
            rpc.return_value.request.side_effect = TimeoutError()
            with self.assertRaises(TimeoutError):
                app_server_probe(ROOT)
            stop.assert_called_once_with(process.return_value)

    def test_login_success_does_not_certify_writing_or_model(self):
        with patch('epicbyte.diagnostics.command', return_value={'exit_code': 0, 'stdout': 'ok', 'stderr': ''}), \
             patch('epicbyte.diagnostics.codex_command', return_value=['codex']), \
             patch('epicbyte.diagnostics.validate_git', return_value='develop'), tempfile.TemporaryDirectory() as directory:
            result = doctor(Path(directory))
        self.assertTrue(result['authenticated'])
        self.assertFalse(result['ready_write'])
        self.assertFalse(result['model_execution_verified'])

    def test_windows_probe_requires_real_command_success(self):
        calls = []
        def run(args, cwd):
            calls.append(args)
            return {'exit_code': 1 if 'sandbox' in args else 0, 'stdout': 'ok', 'stderr': 'failure'}
        with patch('epicbyte.diagnostics.command', side_effect=run), \
             patch('epicbyte.diagnostics.codex_command', return_value=['codex']), \
             patch('epicbyte.diagnostics.validate_git', return_value='develop'), \
             patch('epicbyte.diagnostics.app_server_probe', return_value={'account_available': True}):
            result = doctor(ROOT, probe=True)
        self.assertFalse(result['ready_read_only'])
        if __import__('os').name == 'nt':
            sandbox = next(c for c in calls if 'sandbox' in c)
            self.assertIn(':read-only', sandbox)
            self.assertIn('--include-managed-config', sandbox)

    def test_doctor_exit_reports_write_block(self):
        with patch('epicbyte.cli.doctor', return_value={'ready_write': False}), patch('sys.stdout', io.StringIO()):
            self.assertEqual(main(['doctor', '--probe']), 2)

    def test_ownership_error_has_targeted_action_without_mutation(self):
        from epicbyte.safety import SafetyError
        with patch('epicbyte.diagnostics.command', return_value={'exit_code': 1, 'stdout': '', 'stderr': 'Not logged in'}) as run, \
             patch('epicbyte.diagnostics.codex_command', return_value=['codex']), \
             patch('epicbyte.diagnostics.validate_git', side_effect=SafetyError('dubious ownership')):
            result = doctor(ROOT)
        self.assertFalse(result['authenticated'])
        self.assertEqual(result['mission_001_git'], 'dubious ownership')
        self.assertTrue(any('ownership/ACL' in action for action in result['actions']))
        self.assertFalse(any('config' in call.args[0] for call in run.call_args_list))


if __name__ == '__main__':
    unittest.main()
