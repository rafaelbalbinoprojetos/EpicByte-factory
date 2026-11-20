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
    """Responde como os agentes do fluxo 3.0, a partir do marcador AGENT=<nome> das instruções do ensaio."""

    def __init__(self):
        self.calls = []
        self.rounds = {'TASK-001': 0, 'TASK-002': 0}
        self.reviews = {'TASK-001': 0, 'TASK-002': 0}
        self.saw = {'gates_feedback': False, 'locked_feedback': False, 'reviewer_feedback': False, 'guidance': False}

    def execute(self, prompt, workspace, timeout=180, write=False, cancelled=lambda: False):
        agent = prompt.split('AGENT=', 1)[1].split()[0]
        task = next((t for t in ('TASK-001', 'TASK-002') if f'"id": "{t}"' in prompt), None)
        self.calls.append((agent, task, write))
        commands = [{'type': 'commandExecution', 'status': 'completed', 'command': 'npx tsc --noEmit -p .', 'exitCode': 0, 'aggregatedOutput': ''}]
        if agent == 'analyst':
            report = {'summary': 'Landing de ensaio', 'improved_request': 'Hero e rodapé acessíveis', 'options': [], 'improvements': [],
                      'risks': [], 'design_brief': {'visual': 'escuro e dourado'}, **plan()}
        elif agent == 'supervisor':
            report = {'verdict': 'APPROVED', 'evidence': 'Todas as tarefas auditadas'}
        elif agent == 'builder':
            assert write == 'build', 'o Builder precisa trabalhar no modo build (escrita direta no sandbox)'
            report = self.build(task, workspace, prompt)
        elif agent == 'recovery':
            report = {'diagnosis': 'O Builder repete a mesma entrega', 'action': 'retry_with_guidance',
                      'guidance': 'GUIA-RECUPERACAO: ajuste o texto do rodapé e mantenha o teste.', 'question': ''}
        elif agent == 'reviewer':
            report = self.review(task)
        else:
            raise AssertionError(f'agente inesperado no fluxo 3.0: {agent}')
        return Result(json.dumps(report), f'thread-{len(self.calls)}', 'turn-1', commands if agent == 'reviewer' else [])

    def write(self, workspace, files):
        for rel, content in files.items():
            path = Path(workspace) / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding='utf-8')
        return sorted(files)

    def build(self, task, workspace, prompt):
        self.rounds[task] += 1
        round_ = self.rounds[task]
        styles = (ROOT / 'templates/web-react/src/styles.css').read_text(encoding='utf-8')
        good_hero = {'src/styles.css': styles, 'src/sections/Hero.tsx': HERO, 'src/sections/Hero.test.tsx': HERO_TEST, 'src/App.tsx': APP_HERO_ONLY}
        if task == 'TASK-001' and round_ == 1:
            files = self.write(workspace, {'src/styles.css': STYLES_BROKEN})   # build quebra
        elif task == 'TASK-001' and round_ == 2:
            self.saw['gates_feedback'] = 'italic.css' in prompt
            pkg = Path(workspace) / 'package.json'
            data = json.loads(pkg.read_text(encoding='utf-8'))
            data['scripts']['test'] = 'exit 0'   # tenta burlar as verificações
            files = self.write(workspace, {**good_hero, 'package.json': json.dumps(data, indent=2)})
        elif task == 'TASK-001':
            self.saw['locked_feedback'] = 'package.json' in prompt and 'locked_files_reverted' in prompt
            files = self.write(workspace, good_hero)
        elif round_ == 1:
            files = self.write(workspace, {'src/sections/Footer.tsx': FOOTER, 'src/sections/Footer.test.tsx': FOOTER_TEST, 'src/App.tsx': APP})
        else:
            if 'reviewer_feedback' in prompt:
                self.saw['reviewer_feedback'] = True
            if 'GUIA-RECUPERACAO' in prompt:
                self.saw['guidance'] = True
            files = []   # nada a mudar
        return {'summary': f'{task} rodada {round_}', 'files': files, 'checks': [], 'issues': []}

    def review(self, task):
        self.reviews[task] += 1
        if task == 'TASK-002' and not self.saw['guidance']:   # rejeita até a Recuperação orientar
            return {'verdict': 'REJECTED', 'criteria': [{'index': 0, 'status': 'REJECTED', 'evidence': 'Texto do rodapé', 'files': []}],
                    'security': {'verdict': 'APPROVED', 'issues': []}, 'issues': ['Ajustar o texto do rodapé (src/sections/Footer.tsx)']}
        return {**approval(['package.json', 'src/App.tsx']), 'security': {'verdict': 'APPROVED', 'issues': []}}


@unittest.skipUnless(os.environ.get('EPICBYTE_REHEARSAL') == '1', 'Ensaio lento: EPICBYTE_REHEARSAL=1 ou scripts/rehearsal.py')
class WebMissionRehearsal(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT / 'workspaces', prefix='_ensaio-')
        base = Path(self.temp.name)
        self.agents = base / 'agents'
        self.agents.mkdir()
        for name in ('analyst', 'builder', 'reviewer', 'recovery', 'supervisor', 'developer', 'qa'):
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
        blocked = self.events('TASK_BLOCKED') + self.events('MISSION_BLOCKED') + self.events('TASK_ERROR')
        self.assertEqual(mission['state'], 'COMPLETED', f'bloqueios: {blocked}')

        # fluxo 3.0: um Analista, Builder em modo build, Revisor único
        used = {a for a, _, _ in agents.calls}
        self.assertEqual(used, {'analyst', 'builder', 'reviewer', 'recovery', 'supervisor'})
        self.assertEqual(sum(a == 'analyst' for a, _, _ in agents.calls), 1)

        failed = self.events('GATES_FAILED')
        self.assertEqual(failed and failed[0]['failed'], ['build'], 'o build quebrado precisa ser pego pelas verificações')
        self.assertTrue(agents.saw['gates_feedback'], 'o Builder precisa receber a mensagem real do erro do build')

        self.assertEqual(self.events('LOCKED_FILES_REVERTED')[0]['files'], ['package.json'])
        self.assertNotIn('exit 0', (self.workspace / 'package.json').read_text(encoding='utf-8'))
        self.assertTrue(agents.saw['locked_feedback'], 'o Builder precisa saber que o package.json foi desfeito')

        self.assertTrue(agents.saw['reviewer_feedback'], 'o Builder precisa receber os apontamentos do Revisor')
        self.assertEqual(self.events('RECOVERY_DECISION')[0]['action'], 'retry_with_guidance')
        self.assertTrue(agents.saw['guidance'], 'o Builder precisa receber a orientação da Recuperação')

        visual = self.events('VISUAL_CHECK')
        self.assertTrue(visual and not visual[-1].get('skipped'), 'a verificação visual precisa rodar de verdade')
        self.assertTrue(visual[-1]['passed'], f"verificação visual: {visual[-1].get('problems')}")
        self.assertEqual([w['width'] for w in visual[-1]['widths']], [360, 768, 1280, 1920])
        self.assertEqual(len(self.events('TASK_COMMITTED')), 2)
        log = subprocess.run([GIT, '-C', str(self.workspace), 'log', '--format=%s'], capture_output=True, text=True).stdout
        self.assertIn('TASK-001', log)
        self.assertIn('TASK-002', log)
        self.assertTrue((self.workspace / 'dist' / 'index.html').is_file())
        self.assertFalse(subprocess.run([GIT, '-C', str(self.workspace), 'ls-files', 'node_modules', 'dist'], capture_output=True, text=True).stdout.strip())


if __name__ == '__main__':
    unittest.main()
