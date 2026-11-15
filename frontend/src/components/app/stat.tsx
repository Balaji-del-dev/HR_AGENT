import type { ReactNode } from 'react'
import { Link } from 'react-router'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'

const TONES = {
  primary: 'text-primary dark:text-violet', info: 'text-[#2b6fd6] dark:text-info', pink: 'text-[#c7357a] dark:text-pink',
  success: 'text-[#2e8540] dark:text-success', warning: 'text-[#b8610a] dark:text-warning', destructive: 'text-destructive', muted: 'text-muted-foreground',
}

/** Metric card: label and icon, the number, one line of context. */
export function StatTile({ label, value, icon, hint, to, tone = 'primary', loading }: {
  label: string; value: ReactNode; icon: ReactNode; hint?: ReactNode; to?: string; tone?: keyof typeof TONES; loading?: boolean
}) {
  const body = (
    <div className="p-4">
      <div className="flex items-center justify-between gap-3">
        <p className="truncate text-sm font-semibold text-ink-2">{label}</p>
        <span className={cn('[&_svg]:size-4', TONES[tone])}>{icon}</span>
      </div>
      <div className="tabular mt-2 text-2xl leading-8 font-bold text-foreground">{loading ? <Skeleton className="h-8 w-14" /> : value}</div>
      {hint && <p className="mt-1 truncate text-[13px] text-muted-foreground">{hint}</p>}
    </div>
  )
  const shell = 'group block rounded-lg border bg-card shadow-[var(--card-shadow)] transition'
  return to
    ? <Link to={to} className={cn(shell, 'hover:border-primary/40 focus-visible:ring-2 focus-visible:ring-ring outline-none')}>{body}</Link>
    : <div className={shell}>{body}</div>
}
