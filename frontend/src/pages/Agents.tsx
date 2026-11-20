import {ArrowUpRight, Users} from 'lucide-react';
import {PageHeading} from '@/components/layout/AppShell';
import {StateBadge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Panel} from '@/components/ui/panel';
import {useFactory} from '@/hooks/useFactory';
import {agentLabel, dateTime, duration} from '@/lib/format';

export function Agents() {
  const {data, setModal} = useFactory();
  if (!data) return null;
  return (
    <>
      <PageHeading title="Agent Center" description="Os papéis da fábrica, suas instruções e o histórico real de execuções." />
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 2xl:grid-cols-3">
        {data.agents.map((a, i) => {
          const runs = [...data.executions, ...(data.discovery_runs || [])].filter(e => e.agent === a.name);
          const summary = a.responsibilities.split('\n').find(l => l.trim() && !l.startsWith('#'));
          return (
            <Panel key={a.name} className="flex flex-col">
              <div className="flex items-center justify-between">
                <span className="grid size-11 place-items-center rounded-lg border border-[#23485a] bg-[#142f3e] text-[#49b6ce]"><Users size={22} /></span>
                <span className="font-mono text-[10px] text-ink-muted">AGENT / {String(i + 1).padStart(2, '0')}</span>
              </div>
              <h2 className="mb-3 mt-5 text-[18px] font-semibold text-ink-strong">{agentLabel(a.name)}</h2>
              <StateBadge state={runs.some(e => e.status === 'RUNNING') ? 'RUNNING' : 'IDLE'} className="self-start" />
              <p className="my-4 min-h-[60px] text-[13px] leading-relaxed text-ink-muted">{summary}</p>
              <div className="flex justify-between text-[12px]">
                <span>{runs.length} execuções</span>
                <span>{runs.filter(e => e.status === 'COMPLETED').length} concluídas</span>
              </div>
              {runs[0] && (
                <p className="mt-3 text-[11px] text-ink-muted">
                  Última execução: {dateTime(runs[0].started)} · {duration(runs[0].duration || 0)} · {runs[0].mission || 'Concepção de produto'} / {runs[0].task || 'Discovery'}
                </p>
              )}
              <details className="my-4">
                <summary>Responsabilidades</summary>
                <pre className="mt-2 max-h-56">{a.responsibilities}</pre>
              </details>
              <Button variant="link" className="mt-auto self-start" onClick={() => setModal({title: agentLabel(a.name), value: runs})}>
                Execuções e resultados <ArrowUpRight size={14} />
              </Button>
            </Panel>
          );
        })}
      </div>
    </>
  );
}
