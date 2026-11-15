import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

export type Crumb = { label: string; to?: string }

export function Crumbs({ crumbs, className }: { crumbs: Crumb[]; className?: string }) {
  return (
    <nav aria-label="Breadcrumb" className={cn('mb-3 flex flex-wrap items-center gap-1.5 text-[13px]', className)}>
      {crumbs.map((c, i) => (
        <span key={`${c.label}-${i}`} className="flex items-center gap-1.5">
          {i > 0 && <ChevronRight className="size-3.5 text-muted-foreground/70" />}
          {c.to && i < crumbs.length - 1
            ? <Link to={c.to} className="font-semibold text-primary hover:underline dark:text-violet">{c.label}</Link>
            : <span className="font-medium text-muted-foreground">{c.label}</span>}
        </span>
      ))}
    </nav>
  )
}

/** Page title on the left, actions on the right, centred on one line. */
export function PageHeader({ title, description, actions, crumbs, className }: {
  title: ReactNode; description?: ReactNode; actions?: ReactNode; crumbs?: Crumb[]; className?: string
}) {
  return (
    <header className={cn('mb-7', className)}>
      {crumbs && <Crumbs crumbs={crumbs} />}
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-[28px] leading-9 font-bold tracking-[-0.01em] text-foreground">{title}</h1>
          {description && <p className="mt-1.5 max-w-3xl text-sm text-muted-foreground">{description}</p>}
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
    </header>
  )
}

/**
 * A titled section: an 18 px heading over a hairline, content below.
 * `boxed` puts it in a bordered card instead, for dashboards and side panels.
 */
export function Panel({ title, description, action, children, className, bodyClassName, boxed }: {
  title?: ReactNode; description?: ReactNode; action?: ReactNode; children: ReactNode; className?: string; bodyClassName?: string
  boxed?: boolean; flush?: boolean; icon?: ReactNode
}) {
  if (boxed) {
    return (
      <section className={cn('rounded-lg border bg-card shadow-[var(--card-shadow)]', className)}>
        {(title || action) && (
          <div className="flex items-center gap-3 px-5 pt-4 pb-3">
            <div className="min-w-0 flex-1">
              {title && <h2 className="text-base leading-6 font-bold">{title}</h2>}
              {description && <p className="text-[13px] text-muted-foreground">{description}</p>}
            </div>
            {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
          </div>
        )}
        <div className={cn('px-5 pb-5', !title && !action && 'pt-5', bodyClassName)}>{children}</div>
      </section>
    )
  }
  return (
    <section className={cn('min-w-0', className)}>
      {(title || action) && (
        <div className="mb-3.5 flex items-end gap-3 border-b pb-2.5">
          <div className="min-w-0 flex-1">
            {title && <h2 className="text-lg leading-[26px] font-bold">{title}</h2>}
            {description && <p className="mt-0.5 text-[13px] text-muted-foreground">{description}</p>}
          </div>
          {action && <div className="flex shrink-0 items-center gap-2">{action}</div>}
        </div>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  )
}

export function Highlight({ children }: { children: ReactNode; animate?: boolean; late?: boolean }) {
  return <mark className="hl">{children}</mark>
}

export function KeyValue({ items }: { items: [string, ReactNode][] }) {
  return (
    <dl>
      {items.map(([k, v], i) => (
        <div key={`${k}-${i}`} className="grid grid-cols-[150px_minmax(0,1fr)] gap-3 py-[7px]">
          <dt className="text-sm text-muted-foreground">{k}</dt>
          <dd className="min-w-0 text-sm break-words text-foreground">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return <p className={cn('text-xs font-semibold text-muted-foreground', className)}>{children}</p>
}

/** A small chip: skills, sources, roles. */
export function Tag({ children, tone = 'muted', className }: { children: ReactNode; tone?: 'muted' | 'violet' | 'cyan' | 'success' | 'warning' | 'danger'; className?: string }) {
  const tones = {
    muted: 'border border-border bg-muted text-ink-2', violet: 'bg-primary/10 font-semibold text-primary dark:text-violet', cyan: 'bg-[#dcebfe] text-[#1d4fa8] dark:bg-info/15 dark:text-info',
    success: 'bg-[#d7f5dd] text-[#0b6b2b] dark:bg-success/15 dark:text-success', warning: 'bg-[#fcefc7] text-[#8a4b00] dark:bg-warning/15 dark:text-warning', danger: 'bg-[#fde2e1] text-[#a1221a] dark:bg-destructive/15 dark:text-destructive',
  }
  return <span className={cn('inline-flex h-6 items-center gap-1 rounded-[5px] px-2 text-xs font-medium whitespace-nowrap', tones[tone], className)}>{children}</span>
}
