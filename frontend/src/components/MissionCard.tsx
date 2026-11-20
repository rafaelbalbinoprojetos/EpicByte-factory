import {ChevronRight, Layers3} from 'lucide-react';
import {useNavigate} from 'react-router-dom';
import {StateBadge} from '@/components/ui/badge';
import {Empty, ProgressBar} from '@/components/ui/panel';
import {duration, elapsed, progress, title} from '@/lib/format';
import type {Mission} from '@/lib/types';

export function MissionCard({mission}: {mission: Mission}) {
  const navigate = useNavigate();
  const approved = mission.tasks.filter(t => t.state === 'APPROVED').length;
  return (
    <button
      type="button"
      onClick={() => navigate(`/missoes/${mission.id}`)}
      className="group flex w-full min-w-0 cursor-pointer items-center gap-4 rounded-(--radius-card) border border-line-strong bg-surface p-5 text-left text-[#cddbeb] shadow-(--shadow-card) transition-colors hover:border-accent-line"
    >
      <span className="grid size-11 shrink-0 place-items-center rounded-[9px] border border-[#253e53] bg-[#142637] text-[#5e9fb9]">
        <Layers3 size={20} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="flex flex-wrap items-center justify-between gap-x-3 gap-y-2">
          <h3 className="m-0 min-w-0 break-words text-[13px] font-semibold">{title(mission)}</h3>
          <StateBadge state={mission.state} />
        </span>
        <span className="mt-1 block font-mono text-[10px] text-ink-muted">{mission.id}</span>
        <span className="my-3 block"><ProgressBar value={progress(mission)} /></span>
        <span className="flex justify-between gap-3 text-[11px] text-ink-muted">
          <span>{approved}/{mission.tasks.length} tarefas aprovadas</span>
          <span>{progress(mission)}% · {duration(elapsed(mission))}</span>
        </span>
      </span>
      <ChevronRight size={18} className="shrink-0 text-ink-faint transition-transform group-hover:translate-x-0.5" />
    </button>
  );
}

export function MissionList({missions}: {missions: Mission[]}) {
  if (!missions.length) return <Empty>Nenhuma missão neste estado.</Empty>;
  return <div className="flex flex-col gap-3">{missions.map(m => <MissionCard key={m.id} mission={m} />)}</div>;
}
