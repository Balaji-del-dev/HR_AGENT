/** Formatters and small re-exports shared by every page. */
import { Loader2 } from 'lucide-react'

export { StatusBadge as StatusChip } from '@/components/app/status'
export { ErrorAlert } from '@/components/app/states'

export function Loading({ label = 'Loading…' }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
      <Loader2 className="size-4 animate-spin" /> {label}
    </div>
  )
}

export function shortDate(value: string | null | undefined): string {
  if (!value) return '—'
  return new Date(value).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
}

export function relativeTime(value: string | null | undefined): string {
  if (!value) return '—'
  const minutes = Math.round((Date.now() - new Date(value).getTime()) / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} h ago`
  const days = Math.round(hours / 24)
  return days < 30 ? `${days} d ago` : new Date(value).toLocaleDateString()
}

export function money(value: string | number | null | undefined, currency = 'INR'): string {
  if (value === null || value === undefined || value === '') return '—'
  return new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 0 }).format(Number(value))
}
