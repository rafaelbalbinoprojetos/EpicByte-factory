import re
from enum import StrEnum


class TaskState(StrEnum):
    PENDING = 'PENDING'
    READY = 'READY'
    RUNNING = 'RUNNING'
    REVIEW = 'REVIEW'
    TESTING = 'TESTING'
    FIX_REQUIRED = 'FIX_REQUIRED'
    APPROVED = 'APPROVED'
    BLOCKED = 'BLOCKED'
    FAILED = 'FAILED'


class MissionState(StrEnum):
    CREATED = 'CREATED'
    PLANNING = 'PLANNING'
    RUNNING = 'RUNNING'
    PAUSED = 'PAUSED'
    COMPLETED = 'COMPLETED'
    BLOCKED = 'BLOCKED'
    FAILED = 'FAILED'


TASK_TRANSITIONS = {
    'PENDING': {'READY', 'BLOCKED'}, 'READY': {'RUNNING', 'BLOCKED'},
    'RUNNING': {'REVIEW', 'FIX_REQUIRED', 'FAILED', 'BLOCKED'},
    'REVIEW': {'TESTING', 'FIX_REQUIRED', 'BLOCKED', 'FAILED'},
    'TESTING': {'APPROVED', 'FIX_REQUIRED', 'BLOCKED', 'FAILED'},
    'FIX_REQUIRED': {'READY', 'BLOCKED'}, 'BLOCKED': {'READY', 'PENDING'},
    'FAILED': {'READY', 'PENDING'}, 'APPROVED': set(),
}
MISSION_TRANSITIONS = {
    'CREATED': {'PLANNING', 'PAUSED', 'BLOCKED', 'FAILED'},
    'PLANNING': {'RUNNING', 'PAUSED', 'BLOCKED', 'FAILED'},
    'RUNNING': {'PAUSED', 'COMPLETED', 'BLOCKED', 'FAILED'},
    'PAUSED': {'PLANNING', 'RUNNING', 'BLOCKED', 'FAILED'},
    'BLOCKED': {'PLANNING', 'RUNNING', 'PAUSED'},
    'FAILED': {'PLANNING', 'RUNNING'}, 'COMPLETED': set(),
}
# Time ativo (fluxo 3.0). Os demais arquivos de agents/ ficam para histórico e para o Studio.
AGENTS = ('solution_strategist', 'analyst', 'builder', 'reviewer', 'recovery', 'supervisor')


def validate_plan(plan):
    if not isinstance(plan, dict) or not isinstance(plan.get('tasks'), list) or not plan['tasks']:
        raise ValueError('Plano precisa de tasks não vazias')
    if len(plan['tasks']) > 200:
        raise ValueError('Plano excede 200 tarefas')
    tasks = {}
    for task in plan['tasks']:
        if not isinstance(task, dict):
            raise ValueError('Tarefa inválida')
        ident = task.get('id', '')
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', ident) or ident in tasks:
            raise ValueError('ID inválido ou duplicado')
        if task.get('agent') not in ('developer', 'qa'):
            raise ValueError('Agente da tarefa deve ser developer ou qa')
        for field in ('description',):
            if not isinstance(task.get(field), str) or not task[field].strip():
                raise ValueError('Descrição ausente')
        criteria = task.get('acceptance_criteria')
        if not isinstance(criteria, list) or not criteria or not all(isinstance(c, str) and c.strip() for c in criteria):
            raise ValueError('Critérios de aceite ausentes')
        deps = task.get('dependencies')
        if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps) or len(set(deps)) != len(deps):
            raise ValueError('Dependências inválidas')
        if task.get('mode', 'write') not in ('write', 'read-only'):
            raise ValueError('Modo inválido')
        tasks[ident] = task
    visiting, visited = set(), set()
    def visit(ident):
        if ident not in tasks:
            raise ValueError('Dependência desconhecida: ' + ident)
        if ident in visiting:
            raise ValueError('Dependência circular')
        if ident in visited:
            return
        visiting.add(ident)
        for dep in tasks[ident]['dependencies']:
            visit(dep)
        visiting.remove(ident)
        visited.add(ident)
    for ident in tasks:
        visit(ident)
    return plan


def validate_approved_tasks(plan, allowed):
    """Require traceability to the immutable approved feature whitelist."""
    for task in plan['tasks']:
        ids = task.get('feature_ids')
        if not isinstance(ids, list) or not ids or any(not isinstance(k,str) for k in ids) or set(ids) - set(allowed):
            raise ValueError('Tarefa sem vínculo válido ao escopo aprovado')
    return plan
