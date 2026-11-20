"""Ensaio de ponta a ponta de uma missão web, sem modelo de IA.

Usa o template real, `npm ci` real, o sandbox real (escrita e verificações), commits reais
e o motor real. Só os agentes são simulados, e reproduzem de propósito as situações que já
travaram a fábrica numa missão real:
  - Developer quebra o build (import de fonte inexistente) -> verificação falha -> correção;
  - revisores citam package.json como evidência de leitura;
  - QA aprova com comandos de leitura e usa quality_gates;
  - Security Reviewer aprova com os próprios critérios (quantidade diferente da tarefa);
  - Code Reviewer rejeita uma vez e o Developer responde sem edições (nada a mudar).

Lento (instala dependências e roda o sandbox): execute com EPICBYTE_REHEARSAL=1
ou `python scripts/rehearsal.py`. Nenhuma mudança no motor deve entrar sem passar aqui.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from epicbyte.engine import Limits, WorkflowEngine
from epicbyte.provider import Result
from epicbyte.safety import GIT
from epicbyte.storage import Store
from epicbyte.write_backend import apply_edits

ROOT = Path(__file__).resolve().parents[1]

HERO = """import {motion, useReducedMotion} from 'motion/react';
import {Button} from '@/components/ui/button';

export function Hero() {
  const reduce = useReducedMotion();
  return (
    <section aria-labelledby="hero-title" className="grid min-h-screen place-items-center px-6">
      <motion.div initial={reduce ? false : {opacity: 0, y: 12}} animate={{opacity: 1, y: 0}} className="max-w-2xl text-center">
        <h1 id="hero-title" className="font-display text-5xl">Ensaio da fábrica</h1>
        <p className="mt-4 text-ink-muted">Missão web de ponta a ponta sem modelo de IA.</p>
        <Button className="mt-8">Agendar consulta</Button>
      </motion.div>
    </section>
  );
}
"""
HERO_TEST = """import {render, screen} from '@testing-library/react';
import {Hero} from './Hero';

it('mostra o título principal', () => {
  render(<Hero />);
  expect(screen.getByRole('heading', {level: 1, name: 'Ensaio da fábrica'})).toBeInTheDocument();
});
"""
APP = """import {Footer} from '@/sections/Footer';
import {Hero} from '@/sections/Hero';

export function App() {
  return (
    <>
      <main>
        <Hero />
      </main>
      <Footer />
    </>
  );
}
"""
APP_HERO_ONLY = """import {Hero} from '@/sections/Hero';

export function App() {
  return (
    <main>
      <Hero />
    </main>
  );
}
"""
FOOTER = """export function Footer() {
  return (
    <footer aria-labelledby="footer-title" className="border-t px-6 py-10 text-sm text-ink-muted">
      <h2 id="footer-title" className="sr-only">Rodapé</h2>
      <p>Site de demonstração: dados fictícios.</p>
    </footer>
  );
}
"""
FOOTER_TEST = """import {render, screen} from '@testing-library/react';
import {Footer} from './Footer';

it('identifica o rodapé', () => {
  render(<Footer />);
  expect(screen.getByRole('heading', {name: 'Rodapé'})).toBeInTheDocument();
});
"""
STYLES_BROKEN = '@import "tailwindcss";\n@import "@fontsource-variable/cormorant-garamond/italic.css";\n'


def plan():
    task = lambda ident, description, deps: {'id': ident, 'agent': 'developer', 'mode': 'write', 'description': description,
                                            'acceptance_criteria': ['Seção implementada com teste', 'Verificações passam', 'Acessível'],
                                            'dependencies': deps}
    return {'tasks': [task('TASK-001', 'Implementar o Hero', []), task('TASK-002', 'Implementar o Rodapé', ['TASK-001'])]}


def approval(files, count=3):
    return {'verdict': 'APPROVED', 'criteria': [{'index': i, 'status': 'APPROVED', 'evidence': 'Inspecionado e coerente.', 'files': files} for i in range(count)],
            'issues': []}


class ScriptedAgents:
    """Responde como os agentes, a partir do marcador AGENT=<nome> das instruções do ensaio."""

    def __init__(self):
        self.calls = []
        self.dev_rounds = {'TASK-001': 0, 'TASK-002': 0}
        self.code_review_rejected = False

    def execute(self, prompt, workspace, timeout=180, write=False, cancelled=lambda: False):
        agent = prompt.split('AGENT=', 1)[1].split()[0]
        task = next((t for t in ('TASK-001', 'TASK-002') if f'"id": "{t}"' in prompt), None)
        self.calls.append((agent, task))
        commands = [{'type': 'commandExecution', 'status': 'completed', 'command': 'npx tsc --noEmit -p .', 'exitCode': 0, 'aggregatedOutput': ''}]
        if agent == 'planner':
            report = plan()
        elif agent in ('solution_strategist', 'product_owner', 'architect'):
            report = {'summary': 'Escopo aprovado pelo operador', 'acceptance_criteria': ['Hero', 'Rodapé']}
        elif agent == 'supervisor':
            report = {'verdict': 'APPROVED', 'evidence': 'Todas as tarefas auditadas'}
        elif agent == 'developer':
            report = self.develop(task, workspace)
        elif agent == 'code_reviewer' and task == 'TASK-002' and not self.code_review_rejected:
            self.code_review_rejected = True
            report = {'verdict': 'REJECTED', 'criteria': [{'index': 0, 'status': 'REJECTED', 'evidence': 'Revisar texto', 'files': []}], 'issues': ['Revisar texto do rodapé']}
        elif agent == 'security_reviewer':
            report = approval(['package.json', 'src/App.tsx'], count=5)   # critérios próprios, quantidade diferente
        else:   # code_reviewer e qa citam package.json como evidência de leitura
            report = approval(['package.json', 'src/App.tsx'])
        return Result(json.dumps(report), f'thread-{len(self.calls)}', 'turn-1', commands if agent == 'qa' else [])

    def develop(self, task, workspace):
        self.dev_rounds[task] += 1
        round_ = self.dev_rounds[task]
        if task == 'TASK-001' and round_ == 1:
            edits = [{'path': 'src/styles.css', 'content': STYLES_BROKEN}]   # build quebra
        elif task == 'TASK-001':
            styles = Path(ROOT / 'templates/web-react/src/styles.css').read_text(encoding='utf-8')
            edits = [{'path': 'src/styles.css', 'content': styles}, {'path': 'src/sections/Hero.tsx', 'content': HERO},
                     {'path': 'src/sections/Hero.test.tsx', 'content': HERO_TEST}, {'path': 'src/App.tsx', 'content': APP_HERO_ONLY}]
        elif round_ == 1:
            edits = [{'path': 'src/sections/Footer.tsx', 'content': FOOTER}, {'path': 'src/sections/Footer.test.tsx', 'content': FOOTER_TEST},
                     {'path': 'src/App.tsx', 'content': APP}]
        else:
            edits = []   # correção sem nada a mudar
        files = apply_edits(workspace, edits) if edits else []
        return {'summary': f'{task} rodada {round_}', 'files': files, 'issues': []}


@unittest.skipUnless(os.environ.get('EPICBYTE_REHEARSAL') == '1', 'Ensaio lento: EPICBYTE_REHEARSAL=1 ou scripts/rehearsal.py')
class WebMissionRehearsal(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'workspaces', prefix='_ensaio-')
        base = Path(self.temp.name)
        self.agents = base / 'agents'
        self.agents.mkdir()
        for name in ('solution_strategist', 'product_owner', 'architect', 'planner', 'developer', 'code_reviewer', 'qa', 'security_reviewer', 'supervisor'):
            real = (ROOT / 'agents' / f'{name}.md').read_text(encoding='utf-8')
            (self.agents / f'{name}.md').write_text(f'AGENT={name}\n\n{real}', encoding='utf-8')
        self.workspace = base / 'mission'
        self.workspace.mkdir()
        subprocess.run([GIT, 'init', '-b', 'develop', str(self.workspace)], check=True, capture_output=True)
        from epicbyte.web import prepare_workspace
        prepare_workspace(self.workspace, 'web-react')
        self.store = Store(str(base / 'factory.db'))
        self.store.create('m', '# Ensaio\n\nLanding com Hero e Rodapé.', self.workspace)

    def tearDown(self):
        self.store.db.close()
        shutil.rmtree(self.temp.name, ignore_errors=True)

    def events(self, kind):
        return [json.loads(r[0] or '{}') for r in self.store.db.execute('SELECT data FROM events WHERE mission=? AND type=? ORDER BY seq', ('m', kind))]

    def test_web_mission_completes_without_human(self):
        agents = ScriptedAgents()
        WorkflowEngine(self.store, agents, self.agents, Limits(agent_timeout=600, mission_timeout=3600)).run('m')

        mission = self.store.mission('m')
        blocked = self.events('TASK_BLOCKED') + self.events('MISSION_BLOCKED')
        self.assertEqual(mission['state'], 'COMPLETED', f'bloqueios: {blocked}')

        failed = self.events('GATES_FAILED')
        self.assertEqual(failed and failed[0]['failed'], ['build'], 'o build quebrado precisa ser pego pelas verificações')
        build_output = next(g['output'] for g in self.events('QUALITY_GATES')[0]['results'] if g['gate'] == 'build')
        self.assertIn('italic.css', build_output, 'o Developer precisa receber a mensagem real do erro')

        self.assertTrue(self.events('REVIEW_REJECTED'), 'a rejeição do Code Reviewer precisa gerar correção')
        self.assertEqual(len(self.events('TASK_COMMITTED')), 2)
        log = subprocess.run([GIT, '-C', str(self.workspace), 'log', '--format=%s'], capture_output=True, text=True).stdout
        self.assertIn('TASK-001', log)
        self.assertIn('TASK-002', log)
        self.assertTrue((self.workspace / 'dist' / 'index.html').is_file())
        self.assertFalse(subprocess.run([GIT, '-C', str(self.workspace), 'ls-files', 'node_modules', 'dist'], capture_output=True, text=True).stdout.strip())


if __name__ == '__main__':
    unittest.main()
