import {Clock3, FileCheck2, Layers3, Pause, Play, Terminal, Users} from 'lucide-react';
import {useNavigate, useParams} from 'react-router-dom';
import {PageHeading} from '@/components/layout/AppShell';
import {NewMissionButton} from '@/pages/Dashboard';
import {StateBadge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Empty, JsonView, Panel, SectionHeading} from '@/components/ui/panel';
import {useFactory} from '@/hooks/useFactory';
import {AGENT_LABELS, agentLabel, dateTime, duration, elapsed, progress, taskSpec, title} from '@/lib/format';
import type {FactoryState, Mission} from '@/lib/types';
import {cn} from '@/lib/cn';

function stageState(data: FactoryState, mission: Mission, agent: string) {
  const runs = data.executions.filter(e => e.mission === mission.id && e.agent === agent);
  if (runs.some(e => e.status === 'RUNNING')) return 'RUNNING';
  if (runs.some(e => e.status === 'COMPLETED')) return 'COMPLETED';
  return null;
}

function MissionDetail({data, mission}: {data: FactoryState; mission: Mission}) {
  const {busy, operate, setModal} = useFactory();
  return (
    <>
      <Panel className="my-5 flex flex-wrap items-center justify-between gap-4">
        <div>
          <span className="font-mono text-[10px] text-ink-muted">{mission.id}</span>
          <h2 className="my-2 text-[21px] font-semibold text-ink-strong">{title(mission)}</h2>
          <StateBadge state={mission.state} />
        </div>
        <div className="flex flex-wrap gap-3">
          <Button disabled={busy || mission.state !== 'CREATED'} onClick={() => operate(`missions/${mission.id}/start`)}>
            <Play size={15} />Iniciar
          </Button>
          <Button variant="secondary" disabled={busy || ['COMPLETED', 'FAILED', 'PAUSED'].includes(mission.state) || !!mission.pause} onClick={() => operate(`missions/${mission.id}/pause`)}>
            <Pause size={15} />{mission.pause ? 'Pausa solicitada' : 'Pausar'}
          </Button>
          <Button variant="secondary" disabled={busy || !['PAUSED', 'BLOCKED', 'FAILED'].includes(mission.state)} onClick={() => operate(`missions/${mission.id}/resume`)}>
            <Play size={15} />Retomar
          </Button>
        </div>
      </Panel>

      <div className="my-5 flex flex-wrap gap-6 text-[12px] text-[#8aa3b7]">
        <span className="flex items-center gap-2"><Clock3 size={15} />{duration(elapsed(mission))} registrados</span>
        <span>{progress(mission)}% aprovado</span>
        <span className="font-mono text-[11px] [overflow-wrap:anywhere]">{mission.workspace}</span>
      </div>

      <ol className="m-0 mb-6 flex list-none flex-wrap gap-2 p-0" aria-label="Etapas do pipeline">
        {Object.keys(AGENT_LABELS).map(agent => {
          const state = stageState(data, mission, agent);
          return (
            <li
              key={agent}
              className={cn(
                'flex items-center gap-2 rounded-md border px-3 py-1.5 text-[12px]',
                state === 'RUNNING' ? 'border-run-line bg-run-bg text-run' : state === 'COMPLETED' ? 'border-ok-line bg-ok-bg text-ok' : 'border-line-strong bg-surface text-ink-muted',
              )}
            >
              <span className={cn('size-1.5 rounded-full bg-current', state === 'RUNNING' && 'animate-pulse-soft', !state && 'opacity-40')} />
              {AGENT_LABELS[agent]} · {state ?? 'Não executado'}
            </li>
          );
        })}
      </ol>

      {data.briefs?.filter(b => b.mission === mission.id).map(b => (
        <Panel key={b.id} className="mb-6 p-4">
          <details>
            <summary>Escopo aprovado, Design Brief e referências · {b.id}</summary>
            <JsonView value={{approvals: b.approvals, references: b.references, versions: b.versions}} />
          </details>
        </Panel>
      ))}
      <Panel className="mb-6 p-4">
        <details>
          <summary>Objetivo e critérios de aceite</summary>
          <pre className="mt-3">{mission.source}</pre>
        </details>
      </Panel>

      <SectionHeading icon={<Layers3 size={18} />} title="Pipeline de execução" aside="Dependências validadas pelo Python" />
      {mission.tasks.length ? (
        <div className="mb-7 grid grid-cols-1 gap-4 md:grid-cols-2 2xl:grid-cols-3">
          {mission.tasks.map(t => {
            const spec = taskSpec(t.spec);
            return (
              <Panel key={t.id} className="flex flex-col">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px] text-accent">{t.id}</span>
                  <StateBadge state={t.state} />
                </div>
                <h3 className="my-4 text-[13px] font-semibold leading-relaxed">{spec.description}</h3>
                <span className="flex items-center gap-2 text-[12px] text-[#70b5cf]"><Users size={14} />{agentLabel(spec.agent)}</span>
                <p className="my-2 text-[11px] text-ink-muted">Depende de: {spec.dependencies.join(', ') || 'nenhuma'}</p>
                <ul className="m-0 flex-1 pl-4 text-[11px] leading-relaxed text-[#93a8be]">
                  {spec.acceptance_criteria.map(c => <li key={c}>{c}</li>)}
                </ul>
                <div className="mt-4 flex justify-between text-[11px] text-ink-muted">
                  <span>{t.attempts} tentativas</span>
                  <span>{t.fixes} correções</span>
                </div>
                <Button
                  variant="link"
                  className="mt-4 self-start"
                  onClick={() =>
                    setModal({
                      title: `Evidências · ${t.id}`,
                      value: {evidence: data.evidence.filter(e => e.mission === mission.id && e.task === t.id), executions: data.executions.filter(e => e.mission === mission.id && e.task === t.id)},
                    })
                  }
                >
                  <FileCheck2 size={15} />Ver evidências
                </Button>
              </Panel>
            );
          })}
        </div>
      ) : (
        <Empty className="mb-7">O planejamento será produzido pelo motor ao iniciar a missão.</Empty>
      )}

      <Panel>
        <SectionHeading icon={<Terminal size={18} />} title="Logs e correções" />
        <div className="max-h-[500px] overflow-auto">
          {data.events.filter(e => e.mission === mission.id).map(e => (
            <details key={e.seq} className="border-b border-[#243348]">
              <summary className="flex gap-5 font-mono text-[11px]">
                <time className="text-[#6e879f]">{dateTime(e.timestamp)}</time>
                <b className="text-[#8bc3d1]">{e.type}</b>
                <span>{e.task}</span>
              </summary>
              <JsonView value={e.data} className="mb-3" />
            </details>
          ))}
        </div>
      </Panel>
    </>
  );
}

export function MissionControl() {
  const {data} = useFactory();
  const {missionId} = useParams();
  const navigate = useNavigate();
  if (!data) return null;
  const mission = data.missions.find(m => m.id === missionId) ?? (missionId ? undefined : data.missions[0]);
  return (
    <>
      <PageHeading title="Mission Control" description="Orquestração local com estados e evidências persistidos." action={<NewMissionButton />} />
      <label className="max-w-xl">
        Missão
        <select value={mission?.id ?? ''} onChange={e => navigate(`/missoes/${e.target.value}`)}>
          {!mission && <option value="">Selecione…</option>}
          {data.missions.map(m => <option key={m.id} value={m.id}>{title(m)}</option>)}
        </select>
      </label>
      {mission ? <MissionDetail data={data} mission={mission} /> : <Empty className="mt-6">{missionId ? 'Missão não encontrada.' : 'Crie uma missão para acompanhar o pipeline.'}</Empty>}
    </>
  );
}
