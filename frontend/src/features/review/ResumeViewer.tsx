import { useEffect } from 'react'
import { ShieldAlert } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { useApiV1DocumentsSpansList } from '@/shared/api/generated/documents/documents'
import type { Span } from '@/shared/api/generated/model'

/**
 * The resume as a sheet of paper, page by page, with cited evidence marked by the highlighter.
 * Blind mode shows the masked text the models saw (names and contact details hidden).
 */
export function ResumeViewer({ documentId, highlighted, focus, blind }: { documentId: string; highlighted: Set<string>; focus?: string | null; blind: boolean }) {
  const spans = useApiV1DocumentsSpansList(documentId)
  useEffect(() => {
    if (focus) document.getElementById(`span-${focus}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [focus, spans.data])
  if (spans.isLoading) return <div className="space-y-2 glass rounded-xl p-8">{Array.from({ length: 12 }, (_, i) => <Skeleton key={i} className="h-3.5" style={{ width: `${55 + ((i * 37) % 40)}%` }} />)}</div>
  const pages = new Map<number, Span[]>()
  for (const span of spans.data ?? []) pages.set(span.page, [...(pages.get(span.page) ?? []), span])
  return (
    <div className="max-h-[78vh] space-y-4 overflow-y-auto rounded-xl bg-muted/50 p-3 sm:p-5" aria-label="Resume">
      {[...pages.entries()].map(([page, lines]) => (
        <article key={page} className="relative rounded-lg border bg-white px-7 py-8 text-[#1b1e2b] shadow-sm sm:px-10">
          <span className="absolute top-3 right-4 font-mono text-xs text-[#8a90a6]">page {page}</span>
          {lines.map((span) => {
            const text = blind ? span.text_masked : span.text
            const cited = highlighted.has(span.span_id)
            const heading = span.section === 'heading'
            const withheld = (span.flags ?? []).includes('withheld_protected_attribute')
            const injected = (span.flags ?? []).includes('possible_prompt_injection')
            return (
              <p key={span.span_id} id={`span-${span.span_id}`}
                className={cn('text-[14px] leading-[1.75]', heading && 'mt-4 mb-1 text-xs font-semibold tracking-wide text-[#5f6579] uppercase first:mt-0', span.position === 0 && !heading && 'font-heading text-xl font-semibold')}>
                {cited ? <mark key={focus === span.span_id ? `f-${focus}` : 'm'} className={cn('hl bg-transparent text-inherit', focus === span.span_id && 'hl-swipe')}>{text}</mark>
                  : withheld && blind ? <em className="text-[#8a90a6]">withheld from models (protected attribute)</em> : text}
                {injected && <span className="ml-2 inline-flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 align-middle text-xs font-medium text-amber-800"><ShieldAlert className="size-3" /> instruction-like text, ignored</span>}
              </p>
            )
          })}
        </article>
      ))}
    </div>
  )
}
