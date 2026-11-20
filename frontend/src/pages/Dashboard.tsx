import {Activity, ArrowUpRight, CheckCheck, Command, FileCheck2, Plus, Radio, RefreshCw, ShieldCheck, Terminal, Users} from 'lucide-react';
import {useNavigate} from 'react-router-dom';
import {PageHeading} from '@/components/layout/AppShell';
import {AgentChart} from '@/components/AgentChart';
import {MissionList} from '@/components/MissionCard';
import {StateBadge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Eyebrow, Panel, SectionHeading} from '@/components/ui/panel';
import {useFactory} from '@/hooks/useFactory';
import {ACTIVE_STATES, duration, elapsed, timeOnly} from '@/lib/format';
import type {FactoryState} from '@/lib/types';

export function NewMissionButton() {
  const navigate = useNavigate();
  const {busy} = useFactory();
  return <Button disabled={busy} onClick={() => navigate('/nova')}><Plus size={16} />Nova missão</Button>;
}

function Stats({data}: {data: FactoryState}) {
  const running = data.executions.filter(e => e.status === 'RUNNING').length;
  const items = [
    ['Missões ativas', data.missions.filter(m => ACTIVE_STATES.includes(m.state)).length, Radio],
    ['Concluídas', data.missions.filter(m => m.state === 'COMPLETED').length, CheckCheck],
    ['Bloqueadas', data.missions.filter(m => m.state === 'BLOCKED').length, ShieldCheck],
    ['Agentes em execução', running, Users],
  ] as const;
  return (
    <div className="mb-8 grid grid-cols-2 gap-4 xl:grid-cols-4">
      {items.map(([label, value, Icon]) => (
        <Panel key={label} className="p-5">
          <div className="flex items-center justify-between text-[12px] text-ink-muted">
            <span>{label}</span>
            <Icon size={18} className="text-[#438b9e]" />
          </div>
          <strong className="my-3 block text-[34px] font-semibold tracking-tight text-ink-strong">{String(value).padStart(2, '0')}</strong>
          <div className="text-[11px] text-ink-faint">Estado persistido no backend</div>
        </Panel>
      ))}
    </div>
  );
}

export function Dashboard() {
  const {data, busy, operate, setModal} = useFactory();
  const navigate = useNavigate();
  if (!data) return null;
  const certified = !!data.diagnostic.isolation_certified;
  return (
    <>
      <PageHeading title="Visão geral da operação" description="Uma visão clara. Cada agente, cada missão, cada evidência." action={<NewMissionButton />} />
      <Stats data={data} />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(300px,1fr)]">
        <section>
          <SectionHeading
            icon={<Command size={18} />}
            title="Missões recentes"
            aside={<Button variant="link" onClick={() => navigate('/historico')}>Ver histórico <ArrowUpRight size={14} /></Button>}
          />
          <MissionList missions={data.missions.slice(0, 4)} />
        </section>

        <Panel className="border-t-[#347383]">
          <div className="mb-5 flex items-center justify-between text-accent">
            <ShieldCheck size={24} />
            <Eyebrow>Environment health</Eyebrow>
          </div>
          <h2 className="mb-2 mt-0 text-[19px] font-semibold text-ink-strong">{certified ? 'Isolamento certificado' : 'Certificação necessária'}</h2>
          <p className="m-0 text-[13px] leading-relaxed text-ink-muted">O histórico não autoriza novas escritas. Cada execução valida o ambiente e o workspace atuais.</p>
          <div className="mt-4 flex items-center justify-between border-b border-[#233042] py-3.5 text-[12px]">
            <span>Isolamento atual</span>
            <StateBadge state={certified ? 'APPROVED' : 'BLOCKED'} />
          </div>
          <div className="flex items-center justify-between border-b border-[#233042] py-3.5 text-[12px]">
            <span>Tempo acumulado</span>
            <b className="font-mono">{duration(data.missions.reduce((a, m) => a + elapsed(m), 0))}</b>
          </div>
          <Button variant="secondary" className="mt-5 w-full" disabled={busy} onClick={() => operate('diagnostic')}>
            <RefreshCw size={15} />
            Executar diagnóstico
          </Button>
        </Panel>

        <Panel>
          <div className="mb-4 flex flex-wrap gap-4 text-[12px] text-ink-muted">
            <span className="flex items-center gap-1.5"><FileCheck2 size={15} /> QA: {data.executions.filter(e => e.agent === 'qa' && e.status === 'COMPLETED').length} execuções concluídas</span>
            <span>{data.evidence.filter(e => e.role === 'qa').length} evidências de aprovação</span>
          </div>
          <SectionHeading icon={<Activity size={18} />} title="Atividade dos agentes" aside="execuções registradas" />
          <AgentChart executions={data.executions} />
        </Panel>

        <Panel>
          <SectionHeading icon={<Terminal size={18} />} title="Últimos eventos" aside={<span className="font-mono text-[9px] tracking-[0.2em] text-ok">LIVE</span>} />
          <div>
            {data.events.slice(0, 5).map(e => (
              <button
                key={e.seq}
                type="button"
                onClick={() => setModal({title: e.type, value: e})}
                className="flex w-full cursor-pointer items-center gap-3 border-0 border-b border-[#213042] bg-transparent py-3.5 text-left text-[#b7c9d9]"
              >
                <span className="size-1.5 shrink-0 rounded-full bg-[#3b98b2]" />
                <span className="min-w-0">
                  <strong className="block text-[11px] font-medium">{e.type.replaceAll('_', ' ')}</strong>
                  <span className="block font-mono text-[10px] text-ink-muted">{e.mission}</span>
                </span>
                <time className="ml-auto text-[10px] text-[#667d92]">{timeOnly(e.timestamp)}</time>
              </button>
            ))}
            {!data.events.length && <p className="text-[13px] text-ink-muted">Sem eventos registrados.</p>}
          </div>
        </Panel>
      </div>
    </>
  );
}
