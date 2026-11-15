import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'
import { type Crumb, Crumbs } from './page'

export type MetaItem = { icon?: ReactNode; label: string; value: ReactNode }

/**
 * Top of every detail page: who or what this is and its state, the actions on the right,
 * then a row of key facts split by hairlines, then progress.
 */
export function DetailHero({ crumbs, avatar, eyebrow, title, subtitle, badges, meta, actions, children, className }: {
  crumbs?: Crumb[]; avatar?: ReactNode; eyebrow?: ReactNode; title: ReactNode; subtitle?: ReactNode; badges?: ReactNode
  meta?: MetaItem[]; actions?: ReactNode; children?: ReactNode; className?: string
}) {
  return (
    <header className={cn('mb-8', className)}>
      {crumbs && <Crumbs crumbs={crumbs} />}
      <div className="flex flex-col gap-4 lg:flex-row lg:items-center">
        <div className="flex min-w-0 flex-1 items-center gap-4">
          {avatar && <div className="shrink-0">{avatar}</div>}
          <div className="min-w-0">
            {eyebrow && <p className="mb-0.5 text-[13px] font-semibold text-muted-foreground">{eyebrow}</p>}
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-[28px] leading-9 font-bold tracking-[-0.01em] text-foreground">{title}</h1>
              {badges}
            </div>
            {subtitle && <div className="mt-1 text-sm text-muted-foreground">{subtitle}</div>}
          </div>
        </div>
        {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
      </div>
      {meta && meta.length > 0 && (
        <dl className="mt-4 flex flex-wrap gap-y-3 border-t pt-3.5">
          {meta.map((m, i) => (
            <div key={m.label} className={cn('min-w-[120px] pr-5', i > 0 && 'border-l pl-5')}>
              <dt className="text-[13px] text-muted-foreground">{m.label}</dt>
              <dd className="mt-1 text-sm font-medium text-foreground">{m.value}</dd>
            </div>
          ))}
        </dl>
      )}
      {children && <div className="mt-4 border-t pt-4">{children}</div>}
    </header>
  )
}

/** Label and value rows, the way detail pages list facts. */
export function FactList({ items }: { items: MetaItem[] }) {
  return (
    <dl>
      {items.map((m) => (
        <div key={m.label} className="grid grid-cols-[150px_minmax(0,1fr)] gap-3 py-[7px]">
          <dt className="text-sm text-muted-foreground">{m.label}</dt>
          <dd className="text-sm text-foreground">{m.value}</dd>
        </div>
      ))}
    </dl>
  )
}
