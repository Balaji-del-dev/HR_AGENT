import { cn } from '@/lib/utils'

export type StatusCard = { value: string; label: string; count?: number }

/** Status tabs with counts above a list. Picking one filters the list below. */
export function StatusCards({ items, value, onChange, label = 'Filter by status' }: {
  items: StatusCard[]; value: string; onChange: (value: string) => void; label?: string
}) {
  return (
    <div role="group" aria-label={label} className="mb-4 flex flex-wrap gap-2.5">
      {items.map((item) => {
        const on = item.value === value
        return (
          <button key={item.value} type="button" aria-pressed={on} onClick={() => onChange(item.value)}
            className={cn('min-w-[118px] flex-1 rounded-lg bg-card text-left shadow-[0_1px_1px_rgb(0_0_0/0.04)] transition outline-none focus-visible:ring-2 focus-visible:ring-ring',
              on ? 'border-2 border-primary px-[13px] py-[9px]' : 'border border-input px-3.5 py-2.5 hover:border-primary/40')}>
            <span className={cn('block text-[13px] font-semibold', on ? 'text-primary dark:text-violet' : 'text-muted-foreground')}>{item.label}</span>
            <span className="tabular mt-0.5 block text-xl leading-7 font-bold text-foreground">{item.count ?? '—'}</span>
          </button>
        )
      })}
    </div>
  )
}
