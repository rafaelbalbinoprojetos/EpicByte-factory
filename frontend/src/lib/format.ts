import type {Mission, TaskSpec} from './types';

export const AGENT_LABELS: Record<string, string> = {
  solution_strategist: 'Solution Strategist',
  product_owner: 'Product Owner',
  architect: 'Architect',
  planner: 'Planner',
  developer: 'Developer',
  code_reviewer: 'Code Reviewer',
  qa: 'QA',
  security_reviewer: 'Security Reviewer',
  supervisor: 'Supervisor',
};

export const agentLabel = (name: string) => AGENT_LABELS[name] ?? name;

export const title = (m: Mission) => m.source.match(/^#\s+(.+)/m)?.[1] || m.id;

/** Progresso real: tarefas APPROVED / total. Sem tarefas, 0 (nunca inventado). */
export const progress = (m: Mission) =>
  m.tasks.length ? Math.round((m.tasks.filter(t => t.state === 'APPROVED').length / m.tasks.length) * 100) : 0;

export const elapsed = (m: Mission) =>
  m.elapsed + (m.active_since ? Math.max(0, (Date.now() - Date.parse(m.active_since)) / 1000) : 0);

export const duration = (seconds: number) =>
  seconds < 60 ? `${Math.round(seconds)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;

export const dateTime = (value: string) => new Date(value).toLocaleString('pt-BR');

export const timeOnly = (value: string) => new Date(value).toLocaleTimeString('pt-BR');

export function taskSpec(spec: string): TaskSpec {
  try {
    const parsed = JSON.parse(spec);
    return {description: '', agent: '', dependencies: [], acceptance_criteria: [], ...parsed};
  } catch {
    return {description: spec, agent: '', dependencies: [], acceptance_criteria: []};
  }
}

export const ACTIVE_STATES = ['RUNNING', 'PLANNING'];
