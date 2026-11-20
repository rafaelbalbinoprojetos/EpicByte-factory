import json

import os

import time

from dataclasses import dataclass

from datetime import datetime, timezone

from pathlib import Path

from .executor import AgentExecutor

from .model import validate_plan, validate_approved_tasks

from .provider import ProviderError, ProviderUnavailable

from .safety import IsolationPolicy, SafetyError, snapshot, relative_file, within

from .storage import now





@dataclass

class Limits:

    max_executions: int = 100

    max_attempts: int = 4  # initial implementation plus three correction cycles

    max_fixes: int = 3

    agent_timeout: float = 180

    mission_timeout: float = 3600





def limits_for(store, mission):

    row = store.db.execute('SELECT data FROM mission_limits WHERE mission=?', (mission,)).fetchone()

    return Limits(**json.loads(row[0])) if row else Limits()





class ExecutionSupervisor:

    def __init__(self, limits):

        self.limits = limits



    def remaining(self, elapsed):

        remaining = self.limits.mission_timeout - elapsed

        if remaining <= 0:

            raise ProviderError('Limite de duração total atingido')

        return remaining





class RecoveryManager:

    def __init__(self, store):

        self.store = store



    def recover(self, mission):

        store = self.store

        with store.db:

            store.db.execute("UPDATE executions SET status='INTERRUPTED',finished=? WHERE mission=? AND status='RUNNING'", (now(), mission))

        for task in store.tasks(mission):

            if task['state'] in ('RUNNING', 'REVIEW', 'TESTING'):

                store.transition(mission, 'FIX_REQUIRED', task['id'])

                with store.db:

                    store.event(mission, 'RECOVERY_REQUIRED', task['id'], reason='Reinspecionar estado parcial; não presumir rollback')





def audit_approved(report, spec, workspace):

    if report.get('verdict') != 'APPROVED':

        return False

    criteria = report.get('criteria')

    if not isinstance(criteria, list) or len(criteria) != len(spec['acceptance_criteria']):

        return False

    if {c.get('index') for c in criteria if isinstance(c, dict)} != set(range(len(criteria))):

        return False

    for criterion in criteria:

        if criterion.get('status') != 'APPROVED' or not criterion.get('evidence'):

            return False

        paths = criterion.get('files', [])

        if not isinstance(paths, list):

            return False

        for path in paths:

            if not relative_file(workspace, path).is_file():

                return False

    return True





def test_evidence(result):

    # These come from App Server item/completed notifications, never the agent's prose.

    return bool(result.commands) and all(c.get('status') == 'completed' and c.get('exitCode') == 0

                                         and isinstance(c.get('command'), str) and c['command'].strip()

                                         for c in result.commands)





class WorkflowEngine:

    def __init__(self, store, provider, agents_dir, limits=None, isolation=None):

        self.store, self.limits = store, limits or Limits()

        self.executor = AgentExecutor(store, provider, agents_dir, self.limits.agent_timeout, self.limits.max_executions)

        self.isolation = isolation or IsolationPolicy()

        self.supervisor = ExecutionSupervisor(self.limits)

        self.started = 0

        self.base_elapsed = 0



    def call(self, mission, agent, context, task=None, write=False):

        remaining = self.supervisor.remaining(self.base_elapsed + time.monotonic() - self.started)

        if self.store.mission(mission)['pause']:

            raise ProviderError('Pausa solicitada')

        return self.executor.run(mission, agent, context, task, write, remaining)



    def run(self, mission):

        store = self.store

        owner = str(os.getpid())

        # Cross-process lock; stale locks are never stolen automatically.

        with store.db:

            try:

                store.db.execute('INSERT INTO locks VALUES(?,?)', (mission, owner))

            except Exception as error:

                raise ProviderError('Missão já possui worker ou lock pendente; use recover-lock após verificar PID') from error

        self.started = time.monotonic()

        m = store.mission(mission)

        interrupted_elapsed = max(0, (datetime.now(timezone.utc) - datetime.fromisoformat(m['active_since'])).total_seconds()) if m['active_since'] else 0

        with store.db:

            store.db.execute('UPDATE missions SET elapsed=elapsed+?,active_since=? WHERE id=?', (interrupted_elapsed, now(), mission))

        self.base_elapsed = store.mission(mission)['elapsed']

        try:

            workspace = within(self.executor.agents_dir.parent, store.mission(mission)['workspace'])

            if not workspace.is_dir():

                raise SafetyError('Workspace ausente')

            if store.mission(mission)['state'] == 'COMPLETED':

                return

            RecoveryManager(store).recover(mission)

            m = store.mission(mission)

            if m['pause']:

                if m['state'] != 'PAUSED':

                    store.transition(mission, 'PAUSED')

                return

            if m['state'] == 'CREATED':

                store.transition(mission, 'PLANNING')

                m = store.mission(mission)

            if not store.tasks(mission):

                if m['state'] != 'PLANNING':

                    store.transition(mission, 'PLANNING')

                context = {'mission': m['source'], 'contract': {'summary': 'string', 'acceptance_criteria': ['string']}}

                strategy, _ = self.call(mission, 'solution_strategist', {**context, 'scope_policy':'A missão contém o único escopo autorizado. Recomendações são somente informativas e não podem entrar no plano.'})

                product, _ = self.call(mission, 'product_owner', {**context, 'strategy': strategy, 'scope_policy':'Use somente a missão aprovada; exclua recomendações não autorizadas.'})

                architecture, _ = self.call(mission, 'architect', {**context, 'product': product})

                approved_ids = None
                if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='briefs'").fetchone():
                    approval = store.db.execute('SELECT a.data FROM scope_approvals a JOIN briefs b ON b.id=a.brief WHERE b.mission=? ORDER BY a.version DESC LIMIT 1',(mission,)).fetchone()
                    if approval:
                        approved_ids = [f['id'] for f in json.loads(approval[0])['features']]
                        context['approved_feature_ids'] = approved_ids
                        context['task_traceability'] = 'Cada tarefa deve incluir feature_ids: lista não vazia apenas dos IDs aprovados.'
                plan, _ = self.call(mission, 'planner', {**context, 'product': product, 'architecture': architecture,

                    'contract': {'tasks': [{'id': 'TASK-001', 'agent': 'developer|qa', 'mode': 'write|read-only', 'description': 'string', 'acceptance_criteria': ['string'], 'dependencies': []}]}})

                if approved_ids is not None: validate_approved_tasks(plan, approved_ids)

                store.save_plan(mission, validate_plan(plan))

            if store.mission(mission)['state'] != 'RUNNING':

                store.transition(mission, 'RUNNING')

            while True:

                self.supervisor.remaining(self.base_elapsed + time.monotonic() - self.started)

                if store.mission(mission)['pause']:

                    store.transition(mission, 'PAUSED')

                    return

                tasks = store.tasks(mission)

                if all(t['state'] == 'APPROVED' for t in tasks):

                    evidence = [dict(r) for r in store.db.execute("SELECT task,agent,report FROM executions WHERE mission=? AND status='COMPLETED' ORDER BY id", (mission,))]

                    final, _ = self.call(mission, 'supervisor', {'tasks': tasks, 'evidence': evidence, 'contract': {'verdict': 'APPROVED|BLOCKED', 'evidence': 'string'}})

                    if final.get('verdict') != 'APPROVED' or not final.get('evidence'):

                        raise ProviderError('Supervisor não aprovou entrega')

                    store.transition(mission, 'COMPLETED')

                    with store.db:

                        store.event(mission, 'MISSION_COMPLETED')

                    return

                ready = store.ready(mission)

                if not ready:

                    raise ProviderError('Nenhuma tarefa pronta; dependências bloqueadas ou falhas')

                self.execute_task(mission, ready[0])

        except Exception as error:

            state = store.mission(mission)

            target = 'PAUSED' if state['pause'] else 'BLOCKED'

            if state['state'] != target and state['state'] != 'COMPLETED':

                store.transition(mission, target)

            with store.db:

                store.event(mission, 'MISSION_BLOCKED' if target == 'BLOCKED' else 'MISSION_PAUSED', error=str(error))

        finally:

            with store.db:

                store.db.execute('UPDATE missions SET elapsed=elapsed+?,active_since=NULL WHERE id=?', (time.monotonic()-self.started, mission))

                store.db.execute('DELETE FROM locks WHERE mission=? AND owner=?', (mission, owner))



    def execute_task(self, mission, task):

        store, ident = self.store, task['id']

        spec = json.loads(task['spec'])

        workspace = Path(store.mission(mission)['workspace'])

        if task['attempts'] >= self.limits.max_attempts:

            self.block(mission, ident, 'Limite de tentativas')

            return

        write = spec.get('mode', 'write') == 'write' and spec['agent'] == 'developer'

        try:

            if write:

                self.isolation.require_write(workspace)

            before = snapshot(workspace)

            if task['state'] != 'READY':

                store.transition(mission, 'READY', ident)

            store.transition(mission, 'RUNNING', ident)

            with store.db:

                store.db.execute('UPDATE tasks SET attempts=attempts+1 WHERE mission=? AND id=?', (mission, ident))

                store.event(mission, 'TASK_STARTED', ident, before=before)

            previous = [dict(r) for r in store.db.execute('SELECT agent,report,status FROM executions WHERE mission=? AND task=? ORDER BY id DESC LIMIT 8', (mission, ident))]

            context = {'mission': store.mission(mission)['source'], 'task': spec, 'previous': previous,

                       'workspace': str(workspace), 'contract': {'summary': 'string', 'files': ['relative path'], 'issues': ['string']}}

            try:

                developer, dev_result = self.call(mission, spec['agent'], context, ident, write)

            finally:

                # Preserve partial-write evidence even on timeout, pause or invalid JSON.

                after = snapshot(workspace)

                diff = {'before': before, 'after': after, 'modified': sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))}

                with store.db:

                    store.event(mission, 'WORKSPACE_DIFF', ident, **diff)

            self.record_evidence(mission, ident, 'developer', dev_result)

            if not write and before != after:

                raise SafetyError('Read-only agent modified workspace')

            store.transition(mission, 'REVIEW', ident)

            contract = {'verdict': 'APPROVED|REJECTED|BLOCKED', 'criteria': [{'index': 0, 'status': 'APPROVED|REJECTED|BLOCKED', 'evidence': 'string', 'files': []}], 'issues': ['string']}

            context = {**context, 'developer': developer, 'diff': diff, 'contract': contract}

            independent_threads = {dev_result.thread}

            for agent in ('code_reviewer',):

                report, result = self.call(mission, agent, context, ident)

                if result.thread in independent_threads:

                    raise ProviderError('Auditoria deve usar sessão independente')

                independent_threads.add(result.thread)

                if not audit_approved(report, spec, workspace):

                    with store.db:

                        store.event(mission, 'REVIEW_REJECTED', ident, agent=agent, report=report)

                    return self.fix(mission, ident)

                self.record_evidence(mission, ident, agent, result)

            store.transition(mission, 'TESTING', ident)

            report, result = self.call(mission, 'qa', {**context, 'requirement': 'Execute testes reais; registre comandos via ferramentas; declarações não são evidência.'}, ident)

            approved = result.thread not in independent_threads and audit_approved(report, spec, workspace) and test_evidence(result)

            with store.db:

                store.event(mission, 'TESTS_PASSED' if approved else 'TESTS_FAILED', ident, report=report, commands=result.commands)

            if snapshot(workspace) != after:

                raise SafetyError('Auditoria alterou arquivos do workspace')

            if not approved:

                return self.fix(mission, ident)

            self.record_evidence(mission, ident, 'qa', result)
            independent_threads.add(result.thread)
            security, security_result = self.call(mission, 'security_reviewer', context, ident)
            if security_result.thread in independent_threads:
                raise ProviderError('Auditoria deve usar sessão independente')
            if snapshot(workspace) != after:
                raise SafetyError('Auditoria alterou arquivos do workspace')
            if not audit_approved(security, spec, workspace):
                with store.db:
                    store.event(mission, 'REVIEW_REJECTED', ident, agent='security_reviewer', report=security)
                return self.fix(mission, ident)
            self.record_evidence(mission, ident, 'security_reviewer', security_result)

            store.transition(mission, 'APPROVED', ident)

            with store.db:

                store.event(mission, 'TASK_APPROVED', ident, snapshot=after)

        except ProviderUnavailable:

            if next(t for t in store.tasks(mission) if t['id'] == ident)['state'] in ('RUNNING', 'REVIEW', 'TESTING'):

                store.transition(mission, 'FIX_REQUIRED', ident)

            raise

        except SafetyError as error:

            self.block(mission, ident, str(error))

        except Exception as error:

            if store.mission(mission)['pause']:

                raise

            with store.db:

                store.event(mission, 'TASK_ERROR', ident, error=str(error))

            current = next(t for t in store.tasks(mission) if t['id'] == ident)

            if current['state'] in ('RUNNING', 'REVIEW', 'TESTING'):

                self.fix(mission, ident)

            else:

                raise



    def record_evidence(self, mission, task, role, result):

        store = self.store

        attempt = next(t['attempts'] for t in store.tasks(mission) if t['id'] == task)

        execution = store.db.execute("SELECT id FROM executions WHERE mission=? AND task=? AND status='COMPLETED' ORDER BY id DESC LIMIT 1", (mission, task)).fetchone()[0]

        with store.db:

            store.db.execute('INSERT OR REPLACE INTO evidence VALUES(?,?,?,?,?,?)', (mission, task, attempt, role, execution, result.thread))



    def fix(self, mission, task):

        store = self.store

        row = next(t for t in store.tasks(mission) if t['id'] == task)

        if row['fixes'] >= self.limits.max_fixes or row['attempts'] >= self.limits.max_attempts:

            return self.block(mission, task, 'Limite de 3 ciclos de correção ou tentativas atingido')

        store.transition(mission, 'FIX_REQUIRED', task)

        with store.db:

            store.db.execute('UPDATE tasks SET fixes=fixes+1 WHERE mission=? AND id=?', (mission, task))

            store.event(mission, 'FIX_REQUESTED', task, cycle=row['fixes']+1)



    def block(self, mission, task, reason):

        store = self.store

        store.transition(mission, 'BLOCKED', task)

        with store.db:

            store.event(mission, 'TASK_BLOCKED', task, reason=reason)

        # Propagate transitively so dependents never become executable.

        changed = True

        while changed:

            changed = False

            tasks = store.tasks(mission)

            blocked = {t['id'] for t in tasks if t['state'] in ('BLOCKED', 'FAILED')}

            for row in tasks:

                if row['state'] == 'PENDING' and any(d in blocked for d in json.loads(row['spec'])['dependencies']):

                    store.transition(mission, 'BLOCKED', row['id'])

                    with store.db:

                        store.event(mission, 'TASK_BLOCKED', row['id'], reason='Dependência bloqueada')

                    changed = True

