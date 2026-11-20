import {RefreshCw, Settings2, ShieldCheck} from 'lucide-react';
import {PageHeading} from '@/components/layout/AppShell';
import {Button} from '@/components/ui/button';
import {JsonView, Panel, SectionHeading} from '@/components/ui/panel';
import {useFactory} from '@/hooks/useFactory';

export function Settings() {
  const {data, busy, operate} = useFactory();
  if (!data) return null;
  return (
    <>
      <PageHeading title="Settings" description="Diagnóstico do ambiente, versões e limites desta instalação local." />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
        <Panel>
          <SectionHeading icon={<ShieldCheck size={20} />} title="Segurança do ambiente" />
          <p className="mb-4 text-[13px] text-ink-muted">A chave local é mantida somente nesta sessão do navegador. Credenciais do Codex não são expostas.</p>
          <JsonView value={data.diagnostic} />
          <Button className="mt-5" disabled={busy} onClick={() => operate('diagnostic')}><RefreshCw size={16} />Executar diagnóstico</Button>
        </Panel>
        <Panel>
          <SectionHeading icon={<Settings2 size={20} />} title="Configuração local" />
          <h3 className="mb-2 mt-5 text-[13px] font-semibold">Versões</h3>
          <JsonView value={data.versions} />
          <h3 className="mb-2 mt-5 text-[13px] font-semibold">Limites máximos</h3>
          <JsonView value={data.limits} />
          <h3 className="mb-2 mt-5 text-[13px] font-semibold">Workspaces</h3>
          <JsonView value={data.workspaces} />
          <p className="mt-4 text-[11px] text-ink-muted">Pausa cooperativa entre chamadas e durante execução do provedor. Locks após interrupção exigem recover-lock na CLI.</p>
        </Panel>
      </div>
    </>
  );
}
