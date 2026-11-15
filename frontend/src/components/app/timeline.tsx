import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

export type TimelineItem = { id: string; title: ReactNode; detail?: ReactNode; time?: ReactNode; icon?: ReactNode; tone?: 'primary' | 'success' | 'warning' | 'destructive' | 'info' | 'muted' }
const DOT = {
  primary: 'bg-muted text-muted-foreground ring-border', success: 'bg-[#d7f5dd] text-[#0b6b2b] ring-transparent dark:bg-success/15 dark:text-success',
  warning: 'bg-[#fcefc7] text-[#8a4b00] ring-transparent dark:bg-warning/15 dark:text-warning', destructive: 'bg-[#fde2e1] text-[#a1221a] ring-transparent dark:bg-destructive/15 dark:text-destructive',
  info: 'bg-[#dcebfe] text-[#1d4fa8] ring-transparent dark:bg-info/15 dark:text-info', muted: 'bg-muted text-muted-foreground ring-border',
}

/** Activity feed and step history: the order carries meaning, so it is a real list. */
export function Timeline({ items, dense }: { items: TimelineItem[]; dense?: boolean }) {
  return (
    <ol className="relative">
      {items.map((item, i) => (
        <li key={item.id} className={cn('relative flex gap-3', dense ? 'pb-3' : 'pb-4')}>
          {i < items.length - 1 && <span className="absolute top-7 bottom-0 left-[13px] w-px bg-border" aria-hidden />}
          <span className={cn('z-10 grid size-7 shrink-0 place-items-center rounded-full ring-1 ring-inset [&_svg]:size-3.5', DOT[item.tone ?? 'primary'])}>
            {item.icon ?? <span className="size-1.5 rounded-full bg-current" />}
          </span>
          <div className="min-w-0 flex-1 pt-0.5">
            <div className="flex items-baseline gap-2">
              <p className="flex-1 text-sm font-semibold text-foreground">{item.title}</p>
              {item.time && <span className="shrink-0 text-[13px] text-muted-foreground tabular">{item.time}</span>}
            </div>
            {item.detail && <div className="mt-0.5 text-[13px] text-muted-foreground">{item.detail}</div>}
          </div>
        </li>
      ))}
    </ol>
  )
}

/** Progress through a known sequence of stages (a requisition, an offer chain). */
export function Stages({ steps, active, failed }: { steps: string[]; active: number; failed?: boolean }) {
  return (
    <ol className="flex w-full items-center gap-2 overflow-x-auto py-1" aria-label="Progress">
      {steps.map((step, i) => {
        const done = i < active
        const current = i === active
        return (
          <li key={step} className="flex min-w-0 flex-1 items-center gap-2" aria-current={current ? 'step' : undefined}>
            <span className={cn('grid size-7 shrink-0 place-items-center rounded-full text-xs font-semibold ring-1 ring-inset',
              done ? 'bg-primary text-white ring-transparent' : current ? (failed ? 'bg-destructive/10 text-destructive ring-destructive/40' : 'bg-card text-primary ring-2 ring-primary dark:text-violet') : 'bg-card text-muted-foreground ring-input')}>
              {done ? '✓' : i + 1}
            </span>
            <span className={cn('truncate text-sm', current ? 'font-semibold text-foreground' : 'text-muted-foreground')}>{step}</span>
            {i < steps.length - 1 && <span className={cn('h-px min-w-4 flex-1', done ? 'bg-primary' : 'bg-border')} aria-hidden />}
          </li>
        )
      })}
    </ol>
  )
}
