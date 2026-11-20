import copy
import io
import json
import queue
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from epicbyte.cli import ROOT, create_mission, mission_input, doctor
from epicbyte.engine import WorkflowEngine, Limits, RecoveryManager, audit_approved
from epicbyte.model import validate_plan
from epicbyte.provider import Rpc, Result, ProviderError, ProviderUnavailable, IncompleteTurn, collect_turn, CodexProvider
from epicbyte.safety import SafetyError, relative_file, within, validate_git, snapshot
from epicbyte.storage import Store, clean


def plan(count=1, mode='read-only'):
    return {'tasks': [{'id': f'T{i}', 'agent': 'developer', 'mode': mode,
                       'description': 'Inspect fixture', 'acceptance_criteria': ['Fixture exists'],
                       'dependencies': [f'T{i-1}'] if i else []} for i in range(count)]}


def approval():
    return {'verdict': 'APPROVED', 'criteria': [{'index': 0, 'status': 'APPROVED',
             'evidence': 'fixture.txt inspected', 'files': ['fixture.txt']}]}


class MockProvider:
    def __init__(self, reject=0, fail=None, commands=True, same_thread=False):
        self.calls = []
        self.reject, self.fail, self.commands, self.same_thread = reject, fail, commands, same_thread

    def execute(self, prompt, workspace, timeout=180, write=False, cancelled=lambda: False):
        self.calls.append(prompt)
        if self.fail:
            raise self.fail
        if cancelled():
            raise ProviderError('Paused')
        if '— reviewer' in prompt and self.reject:
            self.reject -= 1
            report = {'verdict': 'REJECTED', 'issues': ['Fix fixture inspection']}
        elif '— supervisor' in prompt:
            report = {'verdict': 'APPROVED', 'evidence': 'All tasks audited'}
        elif '— analyst' in prompt:
            report = {'summary': 'Inspect fixture', 'improved_request': 'Inspect fixture', **plan()}
        elif '— recovery' in prompt:
            report = {'diagnosis': 'Repetição', 'action': 'escalate', 'question': 'Como seguir?'}
        else:
            report = {**approval(), 'security': {'verdict': 'APPROVED', 'issues': []}}
        commands = [{'type': 'commandExecution', 'status': 'completed', 'command': 'fixture-test', 'exitCode': 0, 'aggregatedOutput': 'fixture verified'}] if self.commands else []
        return Result(json.dumps(report), 'same' if self.same_thread else f'thread-{len(self.calls)}', 'turn-1', commands)


class Base(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.root = Path(self.temp.name)
        self.workspace = self.root / 'workspace'
        self.workspace.mkdir()
        (self.workspace / 'fixture.txt').write_text('fixture', encoding='utf-8')
        self.db = self.root / 'factory.db'
        self.store = Store(self.db)
        self.store.create('m', 'Inspect fixture', self.workspace)

    def tearDown(self):
        self.store.db.close()
        self.temp.cleanup()

    def engine(self, provider=None, **limits):
        return WorkflowEngine(self.store, provider or MockProvider(), ROOT / 'agents', Limits(**limits))


class PlanTests(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(validate_plan(plan(3)), plan(3))

    def test_invalid_structure(self):
        for value in (None, {}, {'tasks': []}, {'tasks': ['x']}):
            with self.subTest(value=value), self.assertRaises(ValueError):
                validate_plan(value)

    def test_cycles(self):
        p = plan(2)
        p['tasks'][0]['dependencies'] = ['T1']
        with self.assertRaisesRegex(ValueError, 'circular'):
            validate_plan(p)

    def test_unknown_duplicate_and_empty_criteria(self):
        for change in ('unknown', 'duplicate', 'criteria', 'agent', 'mode'):
            p = plan(2)
            if change == 'unknown': p['tasks'][0]['dependencies'] = ['missing']
            if change == 'duplicate': p['tasks'][1]['id'] = 'T0'
            if change == 'criteria': p['tasks'][0]['acceptance_criteria'] = []
            if change == 'agent': p['tasks'][0]['agent'] = 'root'
            if change == 'mode': p['tasks'][0]['mode'] = 'unsafe'
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_plan(p)

    def test_existing_mission_001(self):
        p = json.loads((ROOT / 'missions/mission_001_plan.json').read_text(encoding='utf-8'))
        self.assertEqual(len(validate_plan(p)['tasks']), 6)


class StorageTests(Base):
    def test_approval_requires_current_evidence(self):
        self.store.save_plan('m', plan())
        for state in ('READY', 'RUNNING', 'REVIEW', 'TESTING'):
            self.store.transition('m', state, 'T0')
        with self.assertRaisesRegex(ValueError, 'evidências'):
            self.store.transition('m', 'APPROVED', 'T0')

    def test_persistence_and_atomic_plan(self):
        self.store.save_plan('m', plan(2))
        second = Store(self.db)
        self.assertEqual(len(second.tasks('m')), 2)
        self.assertEqual(second.mission('m')['state'], 'CREATED')
        self.assertEqual(second.db.execute('SELECT count(*) FROM dependencies').fetchone()[0], 1)
        second.db.close()
        with self.assertRaises(ValueError): self.store.save_plan('m', plan())
        self.assertEqual(len(self.store.tasks('m')), 2)

    def test_transitions_and_dependencies(self):
        self.store.save_plan('m', plan(2))
        with self.assertRaises(ValueError): self.store.transition('m', 'COMPLETED')
        with self.assertRaises(ValueError): self.store.transition('m', 'RUNNING', 'T1')
        with self.assertRaises(ValueError): self.store.transition('m', 'READY', 'T1')
        self.store.transition('m', 'READY', 'T0')
        self.assertEqual([t['id'] for t in self.store.ready('m')], ['T0'])

    def test_approved_task_immutable(self):
        self.store.save_plan('m', plan())
        self.engine().run('m')
        with self.assertRaises(ValueError): self.store.transition('m', 'READY', 'T0')
        events = [r[0] for r in self.store.db.execute('SELECT type FROM events')]
        self.assertIn('TASK_APPROVED', events)
        self.assertIn('MISSION_COMPLETED', events)

    def test_redaction(self):
        self.assertEqual(clean({'access_token': 'abc'})['access_token'], '[REDACTED]')
        self.assertNotIn('abc', clean('token=abc'))


class WorkflowTests(Base):
    def test_quota_stops_without_retries(self):
        self.store.save_plan('m', plan())
        provider = MockProvider(fail=ProviderUnavailable('quota'))
        self.engine(provider).run('m')
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(self.store.mission('m')['state'], 'BLOCKED')
        self.assertEqual(self.store.tasks('m')[0]['state'], 'FIX_REQUIRED')

    def test_crash_duration_budget_survives(self):
        self.store.save_plan('m', plan())
        with self.store.db:
            self.store.db.execute("UPDATE missions SET active_since='2020-01-01T00:00:00+00:00' WHERE id='m'")
        self.engine().run('m')
        self.assertEqual(self.store.mission('m')['state'], 'BLOCKED')
        self.assertGreater(self.store.mission('m')['elapsed'], 3600)

    def test_full_workflow_and_dependencies(self):
        self.store.save_plan('m', plan(3))
        provider = MockProvider()
        self.engine(provider).run('m')
        self.assertEqual(self.store.mission('m')['state'], 'COMPLETED')
        self.assertTrue(all(t['state'] == 'APPROVED' for t in self.store.tasks('m')))
        self.assertEqual(len(provider.calls), 7)   # 3 tarefas x (Builder + Revisor) + Supervisor (antes: 13)

    def test_planning_roles(self):
        provider = MockProvider()
        self.engine(provider).run('m')
        self.assertEqual(self.store.mission('m')['state'], 'COMPLETED')
        self.assertEqual(sum('— analyst' in p for p in provider.calls), 1)   # um Analista planeja tudo

    def test_direct_mission_is_explicitly_approved_for_planning(self):
        provider = MockProvider()
        self.engine(provider).run('m')
        planning = [c for c in provider.calls if '— analyst' in c]
        self.assertTrue(planning and all('APROVADO PELO OPERADOR' in c for c in planning))

    def test_correction_then_approval(self):
        self.store.save_plan('m', plan())
        self.engine(MockProvider(reject=1)).run('m')
        task = self.store.tasks('m')[0]
        self.assertEqual((task['state'], task['fixes'], task['attempts']), ('APPROVED', 1, 2))

    def test_three_corrections_block_dependents(self):
        self.store.save_plan('m', plan(3))
        self.engine(MockProvider(reject=100)).run('m')
        self.assertEqual(self.store.mission('m')['state'], 'BLOCKED')
        self.assertEqual(self.store.tasks('m')[0]['attempts'], 4)
        self.assertEqual(self.store.tasks('m')[0]['fixes'], 3)
        self.assertTrue(all(t['state'] == 'BLOCKED' for t in self.store.tasks('m')))

    def test_timeout_agent_and_attempt_limit(self):
        self.store.save_plan('m', plan())
        self.engine(MockProvider(fail=TimeoutError('timeout')), max_attempts=2).run('m')
        self.assertEqual(self.store.tasks('m')[0]['state'], 'BLOCKED')
        self.assertEqual(self.store.tasks('m')[0]['attempts'], 2)
        # tempo esgotado é infraestrutura: repetido até 3 vezes por rodada antes de contar como falha
        self.assertGreaterEqual(self.store.db.execute("SELECT count(*) FROM events WHERE type='INFRA_RETRY'").fetchone()[0], 4)

    def test_missing_real_commands_rejected(self):
        self.store.save_plan('m', plan())
        self.engine(MockProvider(commands=False)).run('m')
        self.assertEqual(self.store.tasks('m')[0]['state'], 'BLOCKED')

    def test_sessions_must_be_independent(self):
        self.store.save_plan('m', plan())
        self.engine(MockProvider(same_thread=True)).run('m')
        self.assertEqual(self.store.tasks('m')[0]['state'], 'BLOCKED')

    def test_execution_and_duration_limits(self):
        self.store.save_plan('m', plan())
        self.engine(max_executions=1).run('m')
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM executions').fetchone()[0], 1)
        self.assertEqual(self.store.mission('m')['state'], 'BLOCKED')

    def test_total_duration(self):
        self.store.save_plan('m', plan())
        self.engine(mission_timeout=0).run('m')
        self.assertEqual(self.store.mission('m')['state'], 'BLOCKED')

    def test_recovery_does_not_rerun_approved(self):
        self.store.save_plan('m', plan(2))
        for target in ('READY', 'RUNNING', 'REVIEW', 'TESTING'):
            self.store.transition('m', target, 'T0')
        # Restore a previously audited checkpoint without replaying its agents.
        with self.store.db:
            self.store.db.execute("UPDATE tasks SET state='APPROVED' WHERE mission='m' AND id='T0'")
        for target in ('READY', 'RUNNING'):
            self.store.transition('m', target, 'T1')
        provider = MockProvider()
        self.engine(provider).run('m')
        self.assertEqual(self.store.mission('m')['state'], 'COMPLETED')
        self.assertEqual(len(provider.calls), 3)   # T1 de leitura: agente + revisor; depois o supervisor
        self.assertEqual(self.store.tasks('m')[0]['attempts'], 0)

    def test_recovery_marks_execution_interrupted(self):
        self.store.save_plan('m', plan())
        self.store.transition('m', 'READY', 'T0')
        self.store.transition('m', 'RUNNING', 'T0')
        with self.store.db:
            self.store.db.execute("INSERT INTO executions(mission,task,status) VALUES('m','T0','RUNNING')")
        RecoveryManager(self.store).recover('m')
        self.assertEqual(self.store.tasks('m')[0]['state'], 'FIX_REQUIRED')
        self.assertEqual(self.store.db.execute('SELECT status FROM executions').fetchone()[0], 'INTERRUPTED')

    def test_pause_and_resume(self):
        self.store.save_plan('m', plan())
        with self.store.db: self.store.db.execute("UPDATE missions SET pause=1 WHERE id='m'")
        provider = MockProvider()
        self.engine(provider).run('m')
        self.assertEqual(self.store.mission('m')['state'], 'PAUSED')
        self.assertEqual(provider.calls, [])
        with self.store.db: self.store.db.execute("UPDATE missions SET pause=0 WHERE id='m'")
        self.engine(provider).run('m')
        self.assertEqual(self.store.mission('m')['state'], 'COMPLETED')

    def test_double_worker(self):
        with self.store.db: self.store.db.execute("INSERT INTO locks VALUES('m','123')")
        with self.assertRaises(ProviderError): self.engine().run('m')

    def test_partial_changes_recorded_on_interruption(self):
        self.store.save_plan('m', plan(mode='write'))
        provider = MockProvider()
        def interrupted(*args, **kwargs):
            (self.workspace / 'partial.txt').write_text('partial', encoding='utf-8')
            raise TimeoutError('interrupted')
        provider.execute = interrupted
        engine = self.engine(provider, max_attempts=1)
        engine.isolation = Mock()
        engine.run('m')
        row = self.store.db.execute("SELECT data FROM events WHERE type='WORKSPACE_DIFF'").fetchone()
        self.assertIn('partial.txt', json.loads(row[0])['modified'])
        self.assertEqual(self.store.tasks('m')[0]['state'], 'BLOCKED')

    def test_write_fail_closed(self):
        self.store.save_plan('m', plan(mode='write'))
        provider = MockProvider()
        self.engine(provider).run('m')
        self.assertEqual(self.store.tasks('m')[0]['state'], 'BLOCKED')
        self.assertEqual(provider.calls, [])


class SafetyTests(Base):
    def test_path_traversal(self):
        for name in ('../outside', '/tmp/x', 'C:/x', 'a\\b', '.git/config', 'NUL', 'x:stream'):
            with self.subTest(name=name), self.assertRaises(SafetyError):
                relative_file(self.workspace, name)
        self.assertEqual(relative_file(self.workspace, 'src/main.py'), self.workspace / 'src/main.py')

    def test_main_and_detached_protected(self):
        for branch in ('main', 'master', '', 'feature'):
            with patch('epicbyte.safety.git', side_effect=[str(self.workspace), branch]):
                with self.assertRaises(SafetyError): validate_git(self.workspace)
        with patch('epicbyte.safety.git', side_effect=[str(self.workspace), 'develop']):
            self.assertEqual(validate_git(self.workspace), 'develop')

    def test_wrong_git_root(self):
        with patch('epicbyte.safety.git', return_value=str(self.root)):
            with self.assertRaises(SafetyError): validate_git(self.workspace)

    def test_hash_evidence_and_missing_file(self):
        first = snapshot(self.workspace)
        (self.workspace / 'fixture.txt').write_text('changed')
        self.assertNotEqual(first, snapshot(self.workspace))
        self.assertTrue(audit_approved(approval(), plan()['tasks'][0], self.workspace))
        (self.workspace / 'fixture.txt').unlink()
        self.assertFalse(audit_approved(approval(), plan()['tasks'][0], self.workspace))

    def test_mission_input_validation(self):
        with self.assertRaises(SafetyError): mission_input(self.root, '../outside.md')
        (self.root / 'empty.md').write_text('')
        with self.assertRaises(ValueError): mission_input(self.root, 'empty.md')


class RpcTests(unittest.TestCase):
    def test_provider_process_cleaned_after_timeout(self):
        process = Mock()
        process.stdin, process.stdout, process.stderr = io.StringIO(), io.StringIO(), io.StringIO()
        process.poll.return_value = None
        process.pid = 100
        with patch('epicbyte.provider.codex_command', return_value=['codex']), \
             patch('epicbyte.provider.subprocess.Popen', return_value=process), \
             patch('epicbyte.provider.subprocess.run') as kill, \
             patch.object(Rpc, 'request', side_effect=TimeoutError('timeout')):
            with self.assertRaises(TimeoutError): CodexProvider().execute('test', ROOT, .01)
            process.wait.assert_called()
            self.assertTrue(process.stdin.closed)

    def rpc(self):
        rpc = Rpc.__new__(Rpc)
        rpc.process = Mock()
        rpc.process.stdin = io.StringIO()
        rpc.process.poll.return_value = None
        rpc.messages = queue.Queue()
        from collections import deque
        rpc.pending = deque()
        rpc.counter = 0
        rpc.reader_error = None
        return rpc

    def test_interleaved_notifications_retained(self):
        rpc = self.rpc()
        event = {'method': 'item/completed', 'params': {'item': {'type': 'agentMessage', 'text': '{}'}}}
        rpc.messages.put(event)
        rpc.messages.put({'id': 1, 'result': {'ok': True}})
        self.assertEqual(rpc.request('turn/start', {}, time.monotonic()+1), {'ok': True})
        self.assertEqual(rpc.next(time.monotonic()+1, lambda: False), event)

    def test_rpc_error(self):
        rpc = self.rpc()
        rpc.messages.put({'id': 1, 'error': {'code': 429, 'message': 'limit'}})
        with self.assertRaises(ProviderError): rpc.request('turn/start', {}, time.monotonic()+1)

    def test_timeout(self):
        with self.assertRaises(TimeoutError): self.rpc().receive(time.monotonic()-.1, lambda: False)

    def test_incomplete_turn(self):
        rpc = self.rpc()
        rpc.messages.put({'method': 'turn/completed', 'params': {'turn': {'id': 't', 'status': 'failed'}}})
        with self.assertRaises(IncompleteTurn): collect_turn(rpc, 's', 't', time.monotonic()+1)

    def test_completed_without_report(self):
        rpc = self.rpc()
        rpc.messages.put({'method': 'turn/completed', 'params': {'turn': {'id': 't', 'status': 'completed'}}})
        with self.assertRaises(IncompleteTurn): collect_turn(rpc, 's', 't', time.monotonic()+1)

    def test_process_exit(self):
        rpc = self.rpc()
        rpc.process.poll.return_value = 1
        with self.assertRaises(IncompleteTurn): rpc.receive(time.monotonic()+1, lambda: False)

    def test_server_requests_denied(self):
        rpc = self.rpc()
        rpc.messages.put({'id': 900, 'method': 'item/commandExecution/requestApproval'})
        with self.assertRaises(SafetyError): rpc.receive(time.monotonic()+1, lambda: False)
        self.assertIn('error', rpc.process.stdin.getvalue())

    def test_final_not_intermediate(self):
        rpc = self.rpc()
        for message in ('intermediate', '{"verdict":"APPROVED"}'):
            rpc.messages.put({'method': 'item/completed', 'params': {'item': {'type': 'agentMessage', 'text': message}}})
        rpc.messages.put({'method': 'turn/completed', 'params': {'turn': {'id': 't', 'status': 'completed'}}})
        self.assertEqual(collect_turn(rpc, 's', 't', time.monotonic()+1).text, '{"verdict":"APPROVED"}')


class Pipeline21Tests(Base):
    def test_agent_execution_order(self):
        self.engine(MockProvider()).run('m')
        agents=[r[0] for r in self.store.db.execute('SELECT agent FROM executions ORDER BY id')]
        self.assertEqual(agents,['analyst','developer','reviewer','supervisor'])


if __name__ == '__main__':
    unittest.main()
