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
from .web import commit_task, is_web, run_gates, run_visual


# Missão escrita pelo operador no formulário técnico: o texto inteiro é o escopo aprovado.
DIRECT_AUTHORIZATION = ('APROVADO PELO OPERADOR: esta missão foi escrita e criada diretamente pelo operador. Todo o conteúdo da missão '
                        '(descrição, critérios de aceite e restrições) está APPROVED para implementação nesta execução. Não exija outra '
                        'aprovação. O plano deve conter tarefas de implementação (agent developer, mode write) que entreguem tudo o que a missão pede. '
                        'Somente recomendações extras, que não estão no texto da missão, continuam fora do escopo.')


ANALYST_CONTRACT = {
    'summary': 'string', 'improved_request': 'string (pedido reescrito, claro e completo)',
    'options': [{'option': 'string', 'pros': 'string', 'cons': 'string', 'chosen': True}],
    'improvements': [{'improvement': 'string', 'adopted': True, 'reason': 'string'}],
    'risks': ['string'], 'design_brief': {'stack': 'string', 'structure': 'string', 'visual': 'string'},
    'tasks': [{'id': 'TASK-001', 'agent': 'developer', 'mode': 'write', 'description': 'string', 'acceptance_criteria': ['string'], 'dependencies': []}],
}
REVIEWER_CONTRACT = {
    'verdict': 'APPROVED|REJECTED',
    'criteria': [{'index': 0, 'status': 'APPROVED|REJECTED', 'evidence': 'string', 'files': ['relative path']}],
    'security': {'verdict': 'APPROVED|REJECTED', 'issues': ['string']},
    'issues': ['string (acionável: o que, onde, como corrigir)'], 'suggestions': ['string'],
}
RECOVERY_CONTRACT = {'diagnosis': 'string', 'action': 'retry_with_guidance|escalate', 'guidance': 'string', 'question': 'string'}
RETRY_NOTE = 'A tentativa anterior falhou por infraestrutura (tempo esgotado ou resposta fora do formato). Seja objetivo e responda somente o JSON do contrato.'
LOCKED = ('package.json', 'package-lock.json', '.npmrc', 'npm-shrinkwrap.json')


def infrastructure_failure(error):
    text = f'{type(error).__name__} {error}'.lower()
    return any(k in text for k in ('tempo', 'timeout', 'timed out', 'json', 'expecting', 'incomplete', 'conexão', 'connection', 'relatório deve ser objeto'))


def revert_locked(workspace):
    """O Builder escreve direto no sandbox; dependências e scripts continuam travados: o motor desfaz qualquer mudança neles."""
    import subprocess
    from .safety import GIT
    status = subprocess.run([GIT, '-C', str(workspace), 'status', '--porcelain', '--', *LOCKED], capture_output=True, text=True, timeout=30)
    changed = [line[3:].strip() for line in status.stdout.splitlines() if line.strip()]
    for name in changed:
        tracked = subprocess.run([GIT, '-C', str(workspace), 'ls-files', '--error-unmatch', name], capture_output=True, timeout=30).returncode == 0
        if tracked:
            subprocess.run([GIT, '-C', str(workspace), 'checkout', '--', name], capture_output=True, timeout=30)
        else:
            (Path(workspace) / name).unlink(missing_ok=True)
    return changed


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
            if not relative_file(workspace, path).exists():   # arquivo ou pasta citados como evidência
                return False
    return True


def security_approved(report, workspace):
    """A revisão de segurança avalia os próprios critérios (caminhos, credenciais, comandos, dependências),
    não os critérios funcionais da tarefa: aprova com veredito APPROVED e todos os critérios aprovados e com evidência."""
    if report.get('verdict') != 'APPROVED':
        return False
    criteria = report.get('criteria')
    if not isinstance(criteria, list) or not criteria:
        return False
    for criterion in criteria:
        if not isinstance(criterion, dict) or criterion.get('status') != 'APPROVED' or not criterion.get('evidence'):
            return False
        paths = criterion.get('files', [])
        if not isinstance(paths, list):
            return False
        for path in paths:
            if not relative_file(workspace, path).exists():   # arquivo ou pasta citados como evidência
                return False
    return True


def test_evidence(result, report=None):
    """Comandos vêm das notificações do App Server, nunca do texto do agente.

    Exige ao menos um comando concluído com código 0. Um comando que falhou só é tolerado
    se o QA o declarou em `fora_do_escopo` (ex.: teste global de uma tarefa futura), com motivo;
    sem essa declaração explícita, qualquer falha reprova a tarefa."""
    commands = result.commands or []
    if not commands or not all(isinstance(c.get('command'), str) and c['command'].strip() for c in commands):
        return False
    ok = [c for c in commands if c.get('status') == 'completed' and c.get('exitCode') == 0]
    if not ok:
        return False
    declared = (report or {}).get('fora_do_escopo') or []
    if not isinstance(declared, list):
        return False
    marks = [str(d.get('comando') if isinstance(d, dict) else d).strip() for d in declared
             if (not isinstance(d, dict) or str(d.get('motivo') or '').strip())]
    marks = [m for m in marks if len(m) >= 6]
    return all(any(m in c['command'] for m in marks) for c in commands if c not in ok)


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
                context = {'mission': m['source']}
                has_brief = bool(store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='briefs'").fetchone()
                                 and store.db.execute('SELECT 1 FROM briefs WHERE mission=?', (mission,)).fetchone())
                if not has_brief:
                    context['authorization'] = DIRECT_AUTHORIZATION
                approved_ids = None
                if store.db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='briefs'").fetchone():
                    approval = store.db.execute('SELECT a.data FROM scope_approvals a JOIN briefs b ON b.id=a.brief WHERE b.mission=? ORDER BY a.version DESC LIMIT 1',(mission,)).fetchone()
                    if approval:
                        approved_ids = [f['id'] for f in json.loads(approval[0])['features']]
                        context['approved_feature_ids'] = approved_ids
                        context['task_traceability'] = 'Cada tarefa deve incluir feature_ids: lista não vazia apenas dos IDs aprovados.'
                if is_web(m['workspace']):
                    context['project'] = 'Projeto web criado do template web-react (React, TypeScript, Tailwind, Motion, GSAP). Leia AGENTS.md no workspace.'
                analysis, _ = self.call_retry(mission, 'analyst', {**context, 'contract': ANALYST_CONTRACT})
                with store.db:
                    store.event(mission, 'ANALYSIS', **{k: analysis.get(k) for k in ('summary', 'improved_request', 'options', 'improvements', 'risks', 'design_brief')})
                plan = {'tasks': analysis.get('tasks')}
                if approved_ids is not None: validate_approved_tasks(plan, approved_ids)
                if not has_brief and is_web(m['workspace']) and not any(isinstance(t, dict) and t.get('agent') == 'developer' and t.get('mode', 'write') == 'write' for t in plan.get('tasks') or []):
                    raise ProviderError('Plano sem nenhuma tarefa de implementação para uma missão aprovada pelo operador')
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
            return self.exhausted(mission, ident, 'Limite de tentativas')
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
            web = is_web(workspace)
            context = {'mission': store.mission(mission)['source'], 'task': spec, 'workspace': str(workspace),
                       'analysis': self.latest(mission, None, 'ANALYSIS'),
                       'contract': {'summary': 'string', 'files': ['relative path'], 'checks': [{'command': 'string', 'exit_code': 0}], 'issues': ['string']}}
            feedback = self.feedback(mission, ident)
            context.update({k: v for k, v in feedback.items() if v})
            if web:
                context['project'] = 'Projeto web do template web-react (leia AGENTS.md). Dependências e package.json são travados.'
            agent = 'builder' if write else spec['agent']
            mode = 'build' if write else False
            try:
                developer, dev_result = self.call_retry(mission, agent, context, ident, mode)
            finally:
                # Preserva a evidência mesmo com tempo esgotado, pausa ou JSON inválido.
                after = snapshot(workspace)
                diff = {'before': before, 'after': after, 'modified': sorted(k for k in before.keys() | after.keys() if before.get(k) != after.get(k))}
                with store.db:
                    store.event(mission, 'WORKSPACE_DIFF', ident, **diff)
            self.record_evidence(mission, ident, 'developer', dev_result)
            if not write and before != after:
                raise SafetyError('Agente somente leitura alterou o workspace')
            if write:
                reverted = revert_locked(workspace)
                if reverted:
                    with store.db:
                        store.event(mission, 'LOCKED_FILES_REVERTED', ident, files=reverted)
                    after = snapshot(workspace)
                    return self.fix(mission, ident)
            gates = None
            if web:
                self.isolation.require_write(workspace)
                gates = run_gates(workspace)
                with store.db:
                    store.event(mission, 'QUALITY_GATES', ident, **gates)
                if snapshot(workspace) != after:
                    raise SafetyError('Verificações alteraram arquivos-fonte do workspace')
                if not gates['passed']:
                    with store.db:
                        store.event(mission, 'GATES_FAILED', ident, failed=[g['gate'] for g in gates['results'] if not g['passed']])
                    return self.fix(mission, ident)
                attempt = next(t['attempts'] for t in store.tasks(mission) if t['id'] == ident)
                visual = run_visual(workspace, self.executor.agents_dir.parent / '.factory' / 'evidence' / mission / ident / f'tentativa-{attempt}')
                with store.db:
                    store.event(mission, 'VISUAL_CHECK', ident, **visual)
                if not visual.get('passed'):
                    with store.db:
                        store.event(mission, 'VISUAL_FAILED', ident, problems=visual.get('problems'))
                    return self.fix(mission, ident)
            store.transition(mission, 'REVIEW', ident)
            review_context = {**context, 'builder': developer, 'diff': diff, 'contract': REVIEWER_CONTRACT}
            review_context.pop('reviewer_feedback', None)
            if gates:
                review_context['quality_gates'] = gates
                review_context['visual_evidence'] = self.latest(mission, ident, 'VISUAL_CHECK')
            report, result = self.call_retry(mission, 'reviewer', review_context, ident)
            if result.thread == dev_result.thread:
                raise ProviderError('Revisão deve usar sessão independente')
            if snapshot(workspace) != after:
                raise SafetyError('Revisão alterou arquivos do workspace')
            security = report.get('security') if isinstance(report.get('security'), dict) else {}
            approved = (audit_approved(report, spec, workspace) and security.get('verdict') == 'APPROVED'
                        and (web or test_evidence(result, report)))
            with store.db:
                store.event(mission, 'REVIEW_APPROVED' if approved else 'REVIEW_REJECTED', ident, agent='reviewer', report=report, commands=result.commands)
            if not approved:
                return self.fix(mission, ident)
            self.record_evidence(mission, ident, 'reviewer', result)
            store.transition(mission, 'TESTING', ident)
            store.transition(mission, 'APPROVED', ident)
            with store.db:
                store.event(mission, 'TASK_APPROVED', ident, snapshot=after)
            try:   # a aprovação já vale; falha de commit vira evento, não bloqueia
                commit = commit_task(workspace, f"{ident}: {spec.get('description', '')}")
                if commit:
                    with store.db:
                        store.event(mission, 'TASK_COMMITTED', ident, commit=commit)
            except Exception as error:
                with store.db:
                    store.event(mission, 'COMMIT_SKIPPED', ident, reason=str(error)[:300])
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

    def latest(self, mission, task, kind):
        if task is None:
            row = self.store.db.execute('SELECT data FROM events WHERE mission=? AND type=? ORDER BY seq DESC LIMIT 1', (mission, kind)).fetchone()
        else:
            row = self.store.db.execute('SELECT data FROM events WHERE mission=? AND task=? AND type=? ORDER BY seq DESC LIMIT 1', (mission, task, kind)).fetchone()
        return json.loads(row[0]) if row else None

    def feedback(self, mission, task):
        """O que a rodada anterior desta tarefa revelou: falha das verificações, apontamentos do Revisor e orientação da Recuperação."""
        last_gates = self.latest(mission, task, 'QUALITY_GATES')
        rejected = self.latest(mission, task, 'REVIEW_REJECTED')
        guidance = self.latest(mission, task, 'RECOVERY_GUIDANCE')
        reverted = self.latest(mission, task, 'LOCKED_FILES_REVERTED')
        visual = self.latest(mission, task, 'VISUAL_CHECK')
        return {
            'visual_problems': visual.get('problems') if visual and not visual.get('passed') else None,
            'last_quality_gates': last_gates if last_gates and not last_gates.get('passed') else None,
            'reviewer_feedback': (rejected or {}).get('report', {}).get('issues') if rejected else None,
            'guidance': (guidance or {}).get('guidance'),
            'locked_files_reverted': (reverted or {}).get('files'),
        }

    def call_retry(self, mission, agent, context, task=None, write=False):
        """Falha de infraestrutura (tempo esgotado, resposta fora do formato, conexão) não é erro da tarefa:
        repete o mesmo agente até 2 vezes antes de deixar a falha seguir."""
        for attempt in range(3):
            try:
                return self.call(mission, agent, context if attempt == 0 else {**context, 'retry': RETRY_NOTE}, task, write)
            except (ProviderUnavailable, SafetyError):
                raise
            except Exception as error:
                if self.store.mission(mission)['pause'] or not infrastructure_failure(error) or attempt == 2:
                    raise
                with self.store.db:
                    self.store.event(mission, 'INFRA_RETRY', task, agent=agent, error=str(error)[:300], attempt=attempt + 1)

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
            return self.exhausted(mission, task, 'Limite de ciclos de correção ou tentativas atingido')
        store.transition(mission, 'FIX_REQUIRED', task)
        with store.db:
            store.db.execute('UPDATE tasks SET fixes=fixes+1 WHERE mission=? AND id=?', (mission, task))
            store.event(mission, 'FIX_REQUESTED', task, cycle=row['fixes']+1)

    def exhausted(self, mission, task, reason):
        """Antes de chamar um humano, o agente de Recuperação investiga e tenta destravar (uma vez por tarefa)."""
        store = self.store
        if store.db.execute("SELECT 1 FROM events WHERE mission=? AND task=? AND type='RECOVERY_DECISION'", (mission, task)).fetchone():
            return self.block(mission, task, reason + ' (recuperação já tentada)')
        spec = json.loads(next(t for t in store.tasks(mission) if t['id'] == task)['spec'])
        history = [dict(r) for r in store.db.execute('SELECT agent,status,report FROM executions WHERE mission=? AND task=? ORDER BY id DESC LIMIT 10', (mission, task))]
        try:
            decision, _ = self.call_retry(mission, 'recovery', {'mission': store.mission(mission)['source'], 'task': spec, 'history': history,
                                                                'analysis': self.latest(mission, None, 'ANALYSIS'), **self.feedback(mission, task),
                                                                'contract': RECOVERY_CONTRACT}, task)
        except ProviderUnavailable:
            raise
        except Exception as error:
            return self.block(mission, task, f'{reason}; recuperação falhou: {error}')
        with store.db:
            store.event(mission, 'RECOVERY_DECISION', task, **{k: decision.get(k) for k in ('action', 'diagnosis', 'guidance', 'question')})
        if decision.get('action') == 'retry_with_guidance' and str(decision.get('guidance') or '').strip():
            current = next(t for t in store.tasks(mission) if t['id'] == task)['state']
            if current != 'FIX_REQUIRED':
                store.transition(mission, 'FIX_REQUIRED', task)
            with store.db:
                store.db.execute('UPDATE tasks SET attempts=0, fixes=0 WHERE mission=? AND id=?', (mission, task))
                store.event(mission, 'RECOVERY_GUIDANCE', task, guidance=decision['guidance'])
            return None
        question = str(decision.get('question') or reason)
        with store.db:
            store.event(mission, 'NEEDS_OPERATOR', task, question=question)
        return self.block(mission, task, 'Decisão do operador necessária: ' + question)

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
