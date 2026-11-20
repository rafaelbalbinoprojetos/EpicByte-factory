import {useCallback, useState} from 'react';
import {QueryClient, QueryClientProvider} from '@tanstack/react-query';
import {HashRouter, Navigate, Route, Routes} from 'react-router-dom';
import {Rocket} from 'lucide-react';
import {AppShell} from '@/components/layout/AppShell';
import {Button} from '@/components/ui/button';
import {Empty} from '@/components/ui/panel';
import {FactoryProvider, useFactory} from '@/hooks/useFactory';
import {Agents} from '@/pages/Agents';
import {Creator} from '@/pages/Creator';
import {Dashboard} from '@/pages/Dashboard';
import {History} from '@/pages/History';
import {MissionControl} from '@/pages/MissionControl';
import {Settings} from '@/pages/Settings';

const ACCESS_KEY = 'epicbyte-access';

/** A chave chega no fragmento (#access=...) e fica só no sessionStorage desta aba. */
function initialAccess() {
  const value = new URLSearchParams(location.hash.slice(1)).get('access');
  if (value) {
    sessionStorage.setItem(ACCESS_KEY, value);
    history.replaceState(null, '', location.pathname);
  }
  return value || sessionStorage.getItem(ACCESS_KEY) || '';
}

function Login({onAccess}: {onAccess: (value: string) => void}) {
  return (
    <main className="mx-auto max-w-md px-6 pt-[15vh]">
      <Rocket size={40} className="text-accent" />
      <h1 className="my-3 text-[28px] font-semibold text-ink-strong">EpicByte Factory</h1>
      <p className="text-[13px] text-ink-muted">Digite a senha da fábrica (ou abra o endereço com a chave exibido pelo inicializador).</p>
      <form
        className="mt-8 flex flex-col gap-4"
        onSubmit={e => {
          e.preventDefault();
          const value = String(new FormData(e.currentTarget).get('access') || '');
          sessionStorage.setItem(ACCESS_KEY, value);
          onAccess(value);
        }}
      >
        <label>Senha de acesso<input name="access" type="password" required autoComplete="off" /></label>
        <Button type="submit" className="w-full">Conectar</Button>
      </form>
    </main>
  );
}

function Routed() {
  const {data, networkError, disconnect} = useFactory();
  if (!data && /acesso negado|Sessão expirada/i.test(networkError)) {
    return (
      <main className="mx-auto max-w-md px-6 pt-[15vh]">
        <div role="alert" className="mb-5 rounded-md border border-danger-line bg-danger-bg px-4 py-3 text-[13px] text-danger">Senha incorreta ou sessão expirada.</div>
        <Button className="w-full" onClick={disconnect}>Tentar outra senha</Button>
      </main>
    );
  }
  if (!data) return <div className="p-10"><Empty loading>Carregando operação local…</Empty></div>;
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<Dashboard />} />
        <Route path="missoes" element={<MissionControl />} />
        <Route path="missoes/:missionId" element={<MissionControl />} />
        <Route path="agentes" element={<Agents />} />
        <Route path="nova" element={<Creator />} />
        <Route path="historico" element={<History />} />
        <Route path="configuracoes" element={<Settings />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export function App() {
  const [client] = useState(() => new QueryClient({defaultOptions: {queries: {retry: false, refetchOnWindowFocus: false, staleTime: Infinity}}}));
  const [access, setAccess] = useState(initialAccess);
  const disconnect = useCallback(() => {
    sessionStorage.removeItem(ACCESS_KEY);
    setAccess('');
  }, []);

  if (!access) return <Login onAccess={setAccess} />;
  return (
    <QueryClientProvider client={client}>
      <HashRouter>
        <FactoryProvider access={access} onDisconnect={disconnect}>
          <Routed />
        </FactoryProvider>
      </HashRouter>
    </QueryClientProvider>
  );
}
