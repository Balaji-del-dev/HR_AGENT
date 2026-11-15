import { CircleHelp, Info } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { StatusBadge } from '@/components/app/status'
import type { CriterionResult } from '@/shared/api/generated/model'

type Evidence = { span_id: string; quote: string }
const LEVEL = { mandatory: 'text-destructive', required: 'text-violet', preferred: 'text-muted-foreground' } as Record<string, string>

/** A job-criteria comparison, not a ranking: each criterion, its status, and the exact line that shows it. No overall score. */
export function CriteriaMatrix({ criteria, onFocus, active }: { criteria: readonly CriterionResult[]; onFocus: (spanId: string) => void; active?: string | null }) {
  return (
    <ol className="divide-y divide-border/70">
      {criteria.map((c) => {
        const evidence = (c.evidence ?? []) as Evidence[]
        return (
          <li key={c.id} className="grid grid-cols-1 gap-2 py-3.5 sm:grid-cols-[170px_minmax(0,1fr)]">
            <div>
              <p className="font-medium">{c.criterion}</p>
              <p className={cn('text-xs font-semibold tracking-wide uppercase', LEVEL[c.level] ?? 'text-muted-foreground')}>{c.level}</p>
            </div>
            <div className="min-w-0 space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge value={c.status} />
                {c.model_status !== c.status && (
                  <Tooltip>
                    <TooltipTrigger className="inline-flex items-center gap-1 text-xs text-warning"><Info className="size-3.5" /> changed by validation</TooltipTrigger>
                    <TooltipContent className="max-w-xs">{c.validation_note || 'The Validation Agent could not confirm the cited line, so the claim was dropped.'}</TooltipContent>
                  </Tooltip>
                )}
              </div>
              {evidence.map((e) => (
                <button key={e.span_id} type="button" onClick={() => onFocus(e.span_id)} aria-label={`Show evidence for ${c.criterion} in the resume`}
                  className={cn('block w-full rounded-lg px-2.5 py-1.5 text-left text-[13px] leading-snug transition hover:bg-accent', active === e.span_id && 'bg-primary/12 ring-1 ring-violet/30')}>
                  <mark className="hl bg-transparent text-inherit">“{e.quote}”</mark>
                </button>
              ))}
              {c.question && <p className="flex items-start gap-1.5 text-[13px] text-muted-foreground"><CircleHelp className="mt-0.5 size-3.5 shrink-0" />{c.question}</p>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}
