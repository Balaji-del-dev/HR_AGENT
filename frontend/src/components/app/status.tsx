import type { ReactNode } from 'react'
import { Check, Clock3, X } from 'lucide-react'
import { cn } from '@/lib/utils'

type Tone = 'ok' | 'bad' | 'wait' | 'live' | 'stage' | 'neutral'
const TONE: Record<string, Tone> = {
  approved: 'ok', completed: 'ok', processed: 'ok', sent: 'ok', scheduled: 'ok', hired: 'ok', documented: 'ok', accepted: 'ok', confirmed: 'ok',
  rejected: 'bad', failed: 'bad', quarantined: 'bad', not_documented: 'bad', budget_exceeded: 'bad', declined: 'bad', denied: 'bad',
  pending: 'wait', pending_approval: 'wait', awaiting_review: 'wait', submitted: 'wait', changes_requested: 'wait', unclear: 'wait',
  running: 'live', queued: 'live', processing: 'live', uploaded: 'live', screening: 'live', applied: 'live', sending: 'live',
  shortlisted: 'stage', interview: 'stage', offer: 'stage', proposed: 'wait', hold: 'wait', open: 'live',
  draft: 'neutral', closed: 'neutral', withdrawn: 'neutral', cancelled: 'neutral', completed_with_flags: 'wait',
}
const STYLE: Record<Tone, string> = {
  ok: 'bg-[#d7f5dd] text-[#0b6b2b] dark:bg-success/15 dark:text-success',
  bad: 'bg-[#fde2e1] text-[#a1221a] dark:bg-destructive/15 dark:text-destructive',
  wait: 'bg-[#fcefc7] text-[#8a4b00] dark:bg-warning/15 dark:text-warning',
  live: 'bg-[#dcebfe] text-[#1d4fa8] dark:bg-info/15 dark:text-info',
  stage: 'bg-[#e9e7fd] text-[#4434b8] dark:bg-primary/20 dark:text-violet',
  neutral: 'bg-[#ebeef1] text-[#414552] dark:bg-muted dark:text-muted-foreground',
}
const ICON: Partial<Record<Tone, ReactNode>> = {
  ok: <Check className="size-3" strokeWidth={2.5} />, bad: <X className="size-3" strokeWidth={2.5} />, wait: <Clock3 className="size-3" strokeWidth={2.5} />,
}

/** A status is a word first and a color second: the label is always shown. */
export function StatusBadge({ value, className }: { value: string | null | undefined; className?: string }) {
  if (!value) return null
  const tone = TONE[value] ?? 'neutral'
  const text = value.replaceAll('_', ' ')
  const label = text.charAt(0).toUpperCase() + text.slice(1)
  return (
    <span className={cn('inline-flex h-[22px] items-center gap-1 rounded-[5px] px-[7px] text-xs font-semibold whitespace-nowrap', STYLE[tone], className)}>
      <span>{label}</span>
      {ICON[tone]}
    </span>
  )
}
