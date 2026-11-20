import json
import re
import sqlite3
from datetime import datetime, timezone
from .model import TASK_TRANSITIONS, MISSION_TRANSITIONS, validate_plan


def now():
    return datetime.now(timezone.utc).isoformat()


def clean(value):
    if isinstance(value, dict):
        return {k: ('[REDACTED]' if re.search(r'token|cookie|password|secret|authorization|api.?key', k, re.I) else clean(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [clean(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'(?i)Bearer\s+\S+|(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}', '[REDACTED]', value)  # sem pegar TASK-001
        value = re.sub(r'(?i)((?:token|password|secret|api_key|authorization)\s*[:=]\s*)[^\s,;]+', r'\1[REDACTED]', value)
    return value


class Store:
    def __init__(self, path, initialize=True):
        self.db = sqlite3.connect(path, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        if not initialize:
            return
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.executescript('''

        CREATE TABLE IF NOT EXISTS missions(id TEXT PRIMARY KEY, source TEXT NOT NULL, workspace TEXT UNIQUE NOT NULL,

          state TEXT NOT NULL, created TEXT NOT NULL, elapsed REAL DEFAULT 0, pause INTEGER DEFAULT 0, plan TEXT);

        CREATE TABLE IF NOT EXISTS tasks(mission TEXT REFERENCES missions(id), id TEXT, spec TEXT NOT NULL,

          state TEXT NOT NULL, attempts INTEGER DEFAULT 0, fixes INTEGER DEFAULT 0, PRIMARY KEY(mission,id));

        CREATE TABLE IF NOT EXISTS dependencies(mission TEXT, task TEXT, dependency TEXT,

          PRIMARY KEY(mission,task,dependency), FOREIGN KEY(mission,task) REFERENCES tasks(mission,id),

          FOREIGN KEY(mission,dependency) REFERENCES tasks(mission,id));

        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY, timestamp TEXT, mission TEXT, task TEXT, type TEXT, data TEXT);

        CREATE TABLE IF NOT EXISTS executions(id INTEGER PRIMARY KEY, mission TEXT, task TEXT, agent TEXT,

          started TEXT, finished TEXT, status TEXT, report TEXT, duration REAL, usage TEXT);

        CREATE TABLE IF NOT EXISTS mission_limits(mission TEXT PRIMARY KEY REFERENCES missions(id), data TEXT NOT NULL);

        CREATE TABLE IF NOT EXISTS checkpoints(mission TEXT PRIMARY KEY, timestamp TEXT, data TEXT);

        CREATE TABLE IF NOT EXISTS locks(mission TEXT PRIMARY KEY, owner TEXT NOT NULL);

        CREATE TABLE IF NOT EXISTS agents(name TEXT PRIMARY KEY, instructions_hash TEXT, registered TEXT);

        CREATE TABLE IF NOT EXISTS evidence(mission TEXT, task TEXT, attempt INTEGER, role TEXT,

          execution INTEGER REFERENCES executions(id), thread TEXT NOT NULL,

          PRIMARY KEY(mission,task,attempt,role), FOREIGN KEY(mission,task) REFERENCES tasks(mission,id));

        ''')
        columns = {row[1] for row in self.db.execute('PRAGMA table_info(missions)')}
        if 'active_since' not in columns:
            self.db.execute('ALTER TABLE missions ADD COLUMN active_since TEXT')
        self.db.commit()

    def event(self, mission, kind, task=None, **data):
        self.db.execute('INSERT INTO events(timestamp,mission,task,type,data) VALUES(?,?,?,?,?)',
                        (now(), mission, task, kind, json.dumps(clean(data), ensure_ascii=False)))

    def create(self, ident, source, workspace):
        with self.db:
            self.db.execute('INSERT INTO missions(id,source,workspace,state,created) VALUES(?,?,?,?,?)',
                            (ident, source, str(workspace), 'CREATED', now()))
            self.event(ident, 'MISSION_CREATED')

    def mission(self, ident):
        row = self.db.execute('SELECT * FROM missions WHERE id=?', (ident,)).fetchone()
        if row is None:
            raise ValueError('Missão desconhecida: ' + ident)
        return dict(row)

    def tasks(self, ident):
        return [dict(r) for r in self.db.execute('SELECT * FROM tasks WHERE mission=? ORDER BY rowid', (ident,))]

    def reopen_blocked(self, mission):
        """Decisão do operador: devolve tarefas BLOCKED/FAILED a PENDING com tentativas zeradas.
        Tarefas APPROVED não mudam; o motor só libera cada uma quando as dependências estiverem aprovadas."""
        if self.mission(mission)['state'] not in ('BLOCKED', 'FAILED', 'PAUSED'):
            raise ValueError('Só missões bloqueadas, com falha ou pausadas podem reabrir tarefas')
        reopened = [t['id'] for t in self.tasks(mission) if t['state'] in ('BLOCKED', 'FAILED')]
        for task in reopened:
            self.transition(mission, 'PENDING', task)
        with self.db:
            if reopened:
                marks = ','.join('?' * len(reopened))
                self.db.execute(f'UPDATE tasks SET attempts=0, fixes=0 WHERE mission=? AND id IN ({marks})', (mission, *reopened))
            self.event(mission, 'TASKS_REOPENED', tasks=reopened)
        return reopened

    def transition(self, mission, target, task=None):
        with self.db:
            if task:
                row = self.db.execute('SELECT state FROM tasks WHERE mission=? AND id=?', (mission, task)).fetchone()
                if row is None:
                    raise ValueError('Tarefa desconhecida')
                current, transitions = row[0], TASK_TRANSITIONS
            else:
                current, transitions = self.mission(mission)['state'], MISSION_TRANSITIONS
            if target not in transitions.get(current, set()):
                raise ValueError(f'Transição inválida {current} -> {target}')
            if task and target in ('READY', 'RUNNING'):
                spec = next(json.loads(t['spec']) for t in self.tasks(mission) if t['id'] == task)
                states = {t['id']: t['state'] for t in self.tasks(mission)}
                if any(states[d] != 'APPROVED' for d in spec['dependencies']):
                    raise ValueError('Dependências não aprovadas')
            if task and target == 'APPROVED':
                attempt = self.db.execute('SELECT attempts FROM tasks WHERE mission=? AND id=?', (mission, task)).fetchone()[0]
                proofs = self.db.execute('SELECT role,thread FROM evidence WHERE mission=? AND task=? AND attempt=?', (mission, task, attempt)).fetchall()
                if {p['role'] for p in proofs} != {'developer', 'code_reviewer', 'security_reviewer', 'qa'} or len({p['thread'] for p in proofs}) != 4:
                    raise ValueError('Aprovação exige evidências independentes da tentativa atual')
            if not task and target == 'COMPLETED' and (not self.tasks(mission) or any(t['state'] != 'APPROVED' for t in self.tasks(mission))):
                raise ValueError('Missão possui tarefas não aprovadas')
            if task:
                self.db.execute('UPDATE tasks SET state=? WHERE mission=? AND id=?', (target, mission, task))
            else:
                self.db.execute('UPDATE missions SET state=? WHERE id=?', (target, mission))
            self.event(mission, 'STATE_CHANGED', task, previous=current, state=target)
            self.db.execute('INSERT OR REPLACE INTO checkpoints VALUES(?,?,?)',
                            (mission, now(), json.dumps({'task': task, 'state': target})))

    def save_plan(self, mission, plan):
        validate_plan(plan)
        with self.db:
            if self.tasks(mission):
                raise ValueError('Plano já persistido')
            for task in plan['tasks']:
                self.db.execute('INSERT INTO tasks(mission,id,spec,state) VALUES(?,?,?,?)',
                                (mission, task['id'], json.dumps(task), 'PENDING'))
            for task in plan['tasks']:
                for dep in task['dependencies']:
                    self.db.execute('INSERT INTO dependencies VALUES(?,?,?)', (mission, task['id'], dep))
            self.db.execute('UPDATE missions SET plan=? WHERE id=?', (json.dumps(plan), mission))
            self.event(mission, 'PLAN_GENERATED', count=len(plan['tasks']))

    def ready(self, mission):
        tasks = self.tasks(mission)
        states = {t['id']: t['state'] for t in tasks}
        return [t for t in tasks if t['state'] in ('PENDING', 'READY', 'FIX_REQUIRED')
                and all(states[d] == 'APPROVED' for d in json.loads(t['spec'])['dependencies'])]
