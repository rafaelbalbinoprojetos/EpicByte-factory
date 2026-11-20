import type {HTMLAttributes, ReactNode} from 'react';
import {LoaderCircle} from 'lucide-react';
import {cn} from '@/lib/cn';

/** Card com profundidade moderada e glassmorphism discreto. */
export function Panel({className, ...props}: HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={cn('rounded-(--radius-card) border border-line-strong bg-[linear-gradient(130deg,#111b28e6,#0e1621f5)] p-6 shadow-(--shadow-card) backdrop-blur-[6px]', className)}
      {...props}
    />
  );
}

export function SectionHeading({icon, title, aside, className}: {icon?: ReactNode; title: ReactNode; aside?: ReactNode; className?: string}) {
  return (
    <div className={cn('mb-4 flex items-center justify-between gap-3', className)}>
      <h2 className="m-0 flex items-center gap-2.5 text-[15px] font-semibold text-ink-strong [&_svg]:text-[#5e9db4]">
        {icon}
        {title}
      </h2>
      {aside && <div className="text-[12px] text-ink-muted">{aside}</div>}
    </div>
  );
}

export function Empty({children, loading, className}: {children: ReactNode; loading?: boolean; className?: string}) {
  return (
    <div className={cn('flex items-center justify-center gap-3 rounded-lg border border-dashed border-[#28394d] p-10 text-center text-[13px] text-ink-muted', className)}>
      {loading && <LoaderCircle className="animate-spin" size={18} />}
      {children}
    </div>
  );
}

export function Eyebrow({children, className}: {children: ReactNode; className?: string}) {
  return <div className={cn('font-mono text-[10px] uppercase tracking-[0.18em] text-[#5d8299]', className)}>{children}</div>;
}

export function JsonView({value, className}: {value: unknown; className?: string}) {
  let data = value;
  if (typeof value === 'string') {
    try {
      data = JSON.parse(value);
    } catch {
      data = value;
    }
  }
  return <pre className={className}>{typeof data === 'string' ? data : JSON.stringify(data, null, 2)}</pre>;
}

export function ProgressBar({value}: {value: number}) {
  return (
    <div className="h-[3px] overflow-hidden rounded bg-[#223144]" role="progressbar" aria-valuenow={value} aria-valuemin={0} aria-valuemax={100}>
      <div className="h-full bg-accent transition-[width] duration-500" style={{width: `${value}%`}} />
    </div>
  );
}
