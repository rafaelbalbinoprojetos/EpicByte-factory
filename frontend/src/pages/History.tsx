import {PageHeading} from '@/components/layout/AppShell';
import {MissionList} from '@/components/MissionCard';
import {StateBadge} from '@/components/ui/badge';
import {Button} from '@/components/ui/button';
import {Empty, Panel, SectionHeading} from '@/components/ui/panel';
import {useFactory} from '@/hooks/useFactory';
import {agentLabel, duration} from '@/lib/format';

export function History() {
  const {data, setModal} = useFactory();
  if (!data) return null;
  return (
    <>
      <PageHeading title="Execution History" description="Missões, tarefas, tentativas, relatórios e testes reais do QA." />
      <SectionHeading title="Missões persistidas" aside={`${data.missions.length} registros`} />
      <MissionList missions={data.missions} />
      <Panel className="mt-8">
        <SectionHeading title="Execuções, testes e tentativas" />
        {data.executions.length ? (
          <div className="overflow-auto">
            <table className="w-full border-collapse text-left text-[12px]">
              <thead>
                <tr className="text-[10px] uppercase tracking-wider text-[#70889d]">
                  {['Agente / tarefa', 'Missão', 'Estado', 'Duração', 'Evidência'].map(h => <th key={h} className="border-b border-[#304055] px-2.5 py-3.5 font-medium">{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {data.executions.map(e => (
                  <tr key={e.id} className="border-b border-[#223246]">
                    <td className="px-2.5 py-4">{agentLabel(e.agent)}<span className="mt-1.5 block font-mono text-[10px] text-ink-muted">{e.task || 'Planejamento / supervisão'}</span></td>
                    <td className="px-2.5 py-4 font-mono text-[11px]">{e.mission}</td>
                    <td className="px-2.5 py-4"><StateBadge state={e.status} /></td>
                    <td className="px-2.5 py-4">{duration(e.duration || 0)}</td>
                    <td className="px-2.5 py-4"><Button variant="link" onClick={() => setModal({title: `Execução ${e.id} · ${agentLabel(e.agent)}`, value: e})}>Ver relatório</Button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>Nenhuma execução registrada.</Empty>
        )}
      </Panel>
    </>
  );
}
