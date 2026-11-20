import type {Brief} from '@/studio';

export type Task = {id: string; state: string; spec: string; attempts: number; fixes: number};

export type Mission = {
  id: string;
  source: string;
  state: string;
  created: string;
  workspace: string;
  elapsed: number;
  active_since: string | null;
  tasks: Task[];
  pause: number;
};

export type Execution = {
  id: number;
  mission: string;
  task: string;
  agent: string;
  started: string;
  finished: string;
  status: string;
  report: string;
  duration: number;
};

export type FactoryEvent = {seq: number; timestamp: string; mission: string; task: string; type: string; data: string};

export type Agent = {name: string; responsibilities: string};

export type TaskSpec = {description: string; agent: string; dependencies: string[]; acceptance_criteria: string[]};

export type FactoryState = {
  briefs?: Brief[];
  discovery_runs?: Execution[];
  missions: Mission[];
  executions: Execution[];
  events: FactoryEvent[];
  evidence: Record<string, unknown>[];
  agents: Agent[];
  diagnostic: Record<string, unknown>;
  workspaces: {id: string; label: string}[];
  limits: Record<string, number>;
  versions: Record<string, string>;
};
