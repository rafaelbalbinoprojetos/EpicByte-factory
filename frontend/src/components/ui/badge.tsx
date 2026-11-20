import type {ReactNode} from 'react';
import {cn} from '@/lib/cn';

const TONES: Record<string, string> = {
  ok: 'text-ok bg-ok-bg border-ok-line',
  run: 'text-run bg-run-bg border-run-line',
  warn: 'text-warn bg-warn-bg border-warn-line',
  idle: 'text-[#9cadc3] bg-[#1c2839] border-[#344155]',
};

const STATE_TONE: Record<string, keyof typeof TONES> = {
  COMPLETED: 'ok', APPROVED: 'ok',
  RUNNING: 'run', PLANNING: 'run', TESTING: 'run', REVIEW: 'run', READY: 'run',
  BLOCKED: 'warn', FAILED: 'warn', FIX_REQUIRED: 'warn',
};

/** Estado persistido no backend, sempre exibido como veio (nunca traduzido para "parecer" melhor). */
export function StateBadge({state, className}: {state: string; className?: string}) {
  const tone = STATE_TONE[state] ?? 'idle';
  const live = tone === 'run';
  return (
    <span className={cn('inline-flex items-center gap-1.5 whitespace-nowrap rounded-[5px] border px-2 py-1 font-mono text-[9px] tracking-wider', TONES[tone], className)}>
      <span className={cn('size-1.5 rounded-full bg-current', live && 'animate-pulse-soft')} aria-hidden />
      {state}
    </span>
  );
}

export function Tag({children, className}: {children: ReactNode; className?: string}) {
  return <span className={cn('inline-flex items-center gap-1.5 rounded-[5px] border px-2 py-1 font-mono text-[9px] tracking-wider', TONES.idle, className)}>{children}</span>;
}
