import type {ReactNode} from 'react';
import {Box, ChevronRight, Command, History, LayoutDashboard, Plus, Settings2, ShieldCheck, Users, X} from 'lucide-react';
import {NavLink, Outlet, useLocation} from 'react-router-dom';
import {AnimatePresence, motion} from 'motion/react';
import {useFactory} from '@/hooks/useFactory';
import {Button} from '@/components/ui/button';
import {Modal} from '@/components/ui/dialog';
import {JsonView} from '@/components/ui/panel';
import {cn} from '@/lib/cn';

export const NAV = [
  {to: '/', label: 'Dashboard', icon: LayoutDashboard},
  {to: '/missoes', label: 'Mission Control', icon: Command},
  {to: '/agentes', label: 'Agent Center', icon: Users},
  {to: '/nova', label: 'Mission Creator', icon: Plus},
  {to: '/historico', label: 'Execution History', icon: History},
  {to: '/configuracoes', label: 'Settings', icon: Settings2},
] as const;

function Sidebar() {
  const {data} = useFactory();
  return (
    <aside className="fixed inset-y-0 left-0 z-20 flex w-16 flex-col border-r border-line bg-sidebar px-2 py-6 lg:w-60 lg:px-4">
      <a href="#/" className="flex items-center gap-3 px-1 text-ink-strong no-underline">
        <span className="grid size-10 shrink-0 place-items-center rounded-[10px] border border-[#205262] bg-[#102a35] text-accent">
          <Box size={22} />
        </span>
        <span className="hidden text-[15px] font-bold tracking-[0.14em] lg:block">
          EPICBYTE
          <span className="mt-1 block text-[10px] font-medium tracking-[0.3em] text-ink-muted">
            FACTORY <b className="text-accent">2.1</b>
          </span>
        </span>
      </a>

      <div className="my-7 hidden items-center gap-2 rounded-[5px] border border-[#233041] px-2.5 py-2.5 text-[9px] tracking-wider text-[#8e9fb4] lg:flex">
        <span className="size-1.5 rounded-full bg-ok shadow-[0_0_9px_#4ed9ba55]" />
        LOCAL WORKSPACE
        <ShieldCheck size={14} className="ml-auto" />
      </div>
      <div className="mb-3 mt-7 hidden px-3 text-[9px] tracking-[0.2em] text-ink-faint lg:mt-0 lg:block">OPERAÇÃO</div>

      <nav className="mt-6 flex flex-col gap-1.5 lg:mt-0" aria-label="Navegação principal">
        {NAV.map(({to, label, icon: Icon}) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            title={label}
            className={({isActive}) =>
              cn(
                'flex items-center justify-center gap-3 rounded-(--radius-control) border px-3 py-3 text-[13px] font-medium no-underline transition-colors lg:justify-start',
                isActive ? 'border-accent-line bg-accent-soft text-[#56cee1]' : 'border-transparent text-[#8597ad] hover:text-ink-strong',
              )
            }
          >
            <Icon size={18} className="shrink-0" />
            <span className="sr-only lg:not-sr-only">{label}</span>
            {to === '/missoes' && (
              <span className="ml-auto hidden rounded border border-[#215363] px-1.5 py-0.5 font-mono text-[10px] lg:inline">{data?.missions.length ?? 0}</span>
            )}
          </NavLink>
        ))}
      </nav>

      <div className="mt-auto hidden px-3 pt-6 text-[#668398] lg:block">
        <ShieldCheck size={20} />
        <strong className="mt-2.5 block text-[12px] text-[#a3b6ca]">Execução protegida</strong>
        <p className="m-0 mt-1 text-[10px]">Python authority · local only</p>
        <span className="font-mono text-[10px]">127.0.0.1 • sem deploy</span>
      </div>
    </aside>
  );
}

function Header() {
  const {connected} = useFactory();
  const {pathname} = useLocation();
  const current = NAV.find(n => (n.to === '/' ? pathname === '/' : pathname.startsWith(n.to)))?.label ?? 'Dashboard';
  return (
    <header className="sticky top-0 z-10 flex h-16 items-center justify-between gap-4 border-b border-line bg-[#0b111ae6] px-4 backdrop-blur md:px-9">
      <div className="flex items-center gap-3 text-[12px] text-ink-faint">
        Factory <ChevronRight size={13} />
        <span className="text-[#bdcada]">{current}</span>
      </div>
      <div className="flex items-center gap-4">
        <span className="flex items-center gap-2 text-[11px] text-[#8fa4b5]">
          <span className={cn('size-1.5 rounded-full', connected ? 'bg-ok' : 'bg-warn animate-pulse-soft')} />
          <span className="hidden sm:inline">{connected ? 'Eventos conectados' : 'SSE desconectado · reconectando'}</span>
        </span>
        <span className="rounded-[7px] border border-[#354459] bg-[#1c2c3d] px-2.5 py-2 text-[11px]">EB</span>
      </div>
    </header>
  );
}

function ErrorBanner() {
  const {error, networkError, clearError, refresh, disconnect} = useFactory();
  const message = error || networkError;
  if (!message) return null;
  return (
    <div role="alert" className="mb-6 flex flex-wrap items-center gap-3 rounded-md border border-danger-line bg-danger-bg px-4 py-3 text-[13px] text-danger">
      <span className="mr-auto">{message}</span>
      <Button variant="ghost" size="sm" onClick={() => refresh().catch(() => undefined)}>Tentar novamente</Button>
      <Button variant="ghost" size="sm" onClick={disconnect}>Reconectar sessão</Button>
      <Button variant="ghost" size="icon" aria-label="Fechar erro" onClick={clearError}><X size={16} /></Button>
    </div>
  );
}

export function AppShell() {
  const {modal, setModal} = useFactory();
  const {pathname} = useLocation();
  return (
    <div className="min-h-screen">
      <Sidebar />
      <div className="ml-16 min-w-0 lg:ml-60">
        <Header />
        <main className="mx-auto max-w-[1750px] px-4 pb-0 pt-8 md:px-9">
          <ErrorBanner />
          <AnimatePresence mode="wait">
            <motion.div key={pathname.split('/')[1] || 'home'} initial={{opacity: 0, y: 6}} animate={{opacity: 1, y: 0}} exit={{opacity: 0}} transition={{duration: 0.18}}>
              <Outlet />
            </motion.div>
          </AnimatePresence>
          <footer className="mt-9 flex flex-wrap justify-between gap-2 border-t border-[#1f2b3c] py-6 text-[9px] tracking-[0.13em] text-[#526b80]">
            <span>EPICBYTE FACTORY <b className="text-[#44a5b9]">2.1</b></span>
            <span>Local orchestration • Evidence-driven execution</span>
          </footer>
        </main>
      </div>
      <Modal open={!!modal} title={modal?.title ?? ''} onClose={() => setModal(null)}>
        <JsonView value={modal?.value} />
      </Modal>
    </div>
  );
}

export function PageHeading({title, description, action}: {title: string; description: string; action?: ReactNode}) {
  return (
    <div className="mb-8 flex flex-wrap items-center justify-between gap-5">
      <div>
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#5d8299]">EPICBYTE / OPERATIONS</div>
        <h1 className="my-2 text-[28px] font-semibold tracking-[-0.02em] text-ink-strong">{title}</h1>
        <p className="m-0 text-[13px] text-ink-muted">{description}</p>
      </div>
      {action}
    </div>
  );
}
