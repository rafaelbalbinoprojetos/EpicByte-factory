import {AlertTriangle, CheckCircle2, Clock3, ExternalLink, Lightbulb, RotateCcw, FileCheck2, Layers3, Pause, Play, ShieldCheck, Terminal, Users, XCircle} from 'lucide-react';
import {useNavigate, useParams} from 'react-router-dom';
import {PageHeading} from '@/components/layout/AppShell';
import {NewMissionButton} from '@/pages/Dashboard';
import {StateBadge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Empty, JsonView, Panel, SectionHeading} from '@/components/ui/panel';
import {useFactory} from '@/hooks/useFactory';
import {AGENT_LABELS, PIPELINE, agentLabel, dateTime, duration, elapsed, progress, taskSpec, title} from '@/lib/format';
import type {FactoryState, GateResult, Mission} from '@/lib/types';
import {cn} from '@/lib/cn';

function stageState(data: FactoryState, mission: Mission, agent: string) {
  const names = agent === 'builder' ? ['builder', 'developer'] : [agent];
  const runs = data.executions.filter(e => e.mission === mission.id && names.includes(e.agent));
  if (runs.some(e => e.status === 'RUNNING')) return 'RUNNING';
  if (runs.some(e => e.status === 'COMPLETED')) return 'COMPLETED';
  return null;
}

function QualityGates({data, mission}: {data: FactoryState; mission: Mission}) {
  const {setModal} = useFactory();
  const last = data.events.find(e => e.mission === mission.id && e.type === 'QUALITY_GATES');
  if (!last) return null;
  let gates: {passed: boolean; results: GateResult[]};
  try {
    gates = JSON.parse(last.data);
  } catch {
    return null;
  }
  return (
    <Panel className="mb-6">
      <SectionHeading
        icon={<ShieldCheck size={18} />}
        title="Verificações de qualidade"
        aside={<span className="font-mono text-[11px]">{last.task} · {dateTime(last.timestamp)}</span>}
      />
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {gates.results.map(g => (
          <button
            key={g.gate}
            type="button"
            onClick={() => setModal({title: `Verificação ${g.gate} · código ${g.exit_code}`, value: g.output})}
            className={cn('flex cursor-pointer items-center gap-2 rounded-md border px-3 py-2.5 text-left text-[12px]', g.passed ? 'border-ok-line bg-ok-bg text-ok' : 'border-warn-line bg-warn-bg text-warn')}
          >
            {g.passed ? <CheckCircle2 size={16} /> : <XCircle size={16} />}
            <span className="font-medium">{g.gate}</span>
            <span className="ml-auto font-mono text-[10px] opacity-80">{g.duration}s</span>
          </button>
        ))}
      </div>
    </Panel>
  );
}

function parse<T>(value: string): T | null {
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

/** Pergunta da Recuperação quando só o operador pode decidir. */
function OperatorQuestion({data, mission}: {data: FactoryState; mission: Mission}) {
  const event = data.events.find(e => e.mission === mission.id && e.type === 'NEEDS_OPERATOR');
  if (!event || mission.state !== 'BLOCKED') return null;
  const question = parse<{question?: string}>(event.data)?.question;
  return (
    <div role="alert" className="mb-6 flex gap-3 rounded-(--radius-card) border border-warn-line bg-warn-bg p-5 text-warn">
      <AlertTriangle size={20} className="mt-0.5 shrink-0" />
      <div>
        <strong className="block text-[14px]">Decisão necessária · {event.task}</strong>
        <p className="m-0 mt-1 text-[13px] leading-relaxed text-ink">{question}</p>
        <p className="m-0 mt-2 text-[12px] text-ink-muted">Ajuste a missão ou responda criando uma nova versão; depois use Reabrir tarefas e Retomar.</p>
      </div>
    </div>
  );
}

type Analysis = {summary?: string; improved_request?: string; options?: {option?: string; chosen?: boolean}[]; improvements?: {improvement?: string; adopted?: boolean}[]; risks?: string[]};

/** O que o Analista entendeu e melhorou no pedido. */
function AnalysisPanel({data, mission}: {data: FactoryState; mission: Mission}) {
  const event = data.events.find(e => e.mission === mission.id && e.type === 'ANALYSIS');
  const analysis = event ? parse<Analysis>(event.data) : null;
  if (!analysis) return null;
  const adopted = (analysis.improvements || []).filter(i => i.adopted !== false);
  return (
    <Panel className="mb-6">
      <SectionHeading icon={<Lightbulb size={18} />} title="Análise do pedido" aside="Analista" />
      {analysis.improved_request && <p className="m-0 text-[13px] leading-relaxed text-ink">{analysis.improved_request}</p>}
      <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-3">
        {[
          ['Abordagem escolhida', (analysis.options || []).filter(o => o.chosen).map(o => o.option)],
          ['Melhorias adotadas', adopted.map(i => i.improvement)],
          ['Riscos tratados', analysis.risks || []],
        ].map(([label, items]) => (
          <div key={label as string}>
            <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[#5d8299]">{label as string}</div>
            <ul className="m-0 pl-4 text-[12px] leading-relaxed text-ink-muted">
              {(items as (string | undefined)[]).filter(Boolean).slice(0, 6).map(item => <li key={item}>{item}</li>)}
            </ul>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function MissionDetail({data, mission}: {data: FactoryState; mission: Mission}) {
  const {busy, operate, setModal} = useFactory();
  const isWeb = !!data.web_missions?.includes(mission.id);
  const built = data.events.some(e => e.mission === mission.id && e.type === 'QUALITY_GATES' && /"gate": "build", "exit_code": 0/.test(e.data));
  async function openSite() {
    const result = await operate(`missions/${mission.id}/preview`);
    if (typeof result?.url === 'string') window.open(result.url, '_blank', 'noopener');
  }
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
          {['BLOCKED', 'FAILED'].includes(mission.state) && mission.tasks.some(t => ['BLOCKED', 'FAILED'].includes(t.state)) && (
            <Button
              variant="secondary"
              disabled={busy}
              title="Devolve as tarefas bloqueadas para pendente com tentativas zeradas. Use quando a falha foi do ambiente ou da fábrica."
              onClick={() => operate(`missions/${mission.id}/reopen`)}
            >
              <RotateCcw size={15} />Reabrir tarefas
            </Button>
          )}
          {isWeb && (
            <Button variant="secondary" disabled={busy || !built} title={built ? 'Abre o build atual numa porta própria' : 'Disponível depois do primeiro build aprovado nas verificações'} onClick={openSite}>
              <ExternalLink size={15} />Abrir site
            </Button>
          )}
        </div>
      </Panel>

      <div className="my-5 flex flex-wrap gap-6 text-[12px] text-[#8aa3b7]">
        <span className="flex items-center gap-2"><Clock3 size={15} />{duration(elapsed(mission))} registrados</span>
        <span>{progress(mission)}% aprovado</span>
        <span className="font-mono text-[11px] [overflow-wrap:anywhere]">{mission.workspace}</span>
      </div>

      <ol className="m-0 mb-6 flex list-none flex-wrap gap-2 p-0" aria-label="Etapas do pipeline">
        {PIPELINE.map(agent => {
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

      <OperatorQuestion data={data} mission={mission} />
      <AnalysisPanel data={data} mission={mission} />
      <QualityGates data={data} mission={mission} />
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
