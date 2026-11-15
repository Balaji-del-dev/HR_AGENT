import { useState, type ReactNode } from 'react'
import { useParams } from 'react-router'
import { CalendarDays, CheckCircle2, ClipboardPen, Hash, ShieldAlert, Star, ThumbsDown, ThumbsUp, Timer, UserRound } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { DetailHero } from '@/components/app/detail'
import { Panel } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import { ErrorAlert, ErrorState, PageSkeleton, SuccessState } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { useApiV1InterviewsRetrieve, useApiV1InterviewsScorecardsCreate } from '@/shared/api/generated/interviews/interviews'
import type { RecommendationEnum } from '@/shared/api/generated/model'
import { shortDate } from '@/shared/ui/common'

const CRITERIA = ['Technical depth', 'Problem solving', 'Communication', 'Collaboration']
const SCALE = ['', 'Little evidence', 'Some evidence', 'Solid', 'Strong', 'Exceptional']
const RECOMMENDATIONS: { value: RecommendationEnum; label: string; icon: ReactNode; tone: string }[] = [
  { value: 'strong_no', label: 'Strong no', icon: <ThumbsDown />, tone: 'data-[on=true]:bg-destructive/15 data-[on=true]:text-destructive data-[on=true]:ring-destructive/40' },
  { value: 'no', label: 'No', icon: <ThumbsDown />, tone: 'data-[on=true]:bg-warning/15 data-[on=true]:text-warning data-[on=true]:ring-warning/40' },
  { value: 'yes', label: 'Yes', icon: <ThumbsUp />, tone: 'data-[on=true]:bg-info/15 data-[on=true]:text-info data-[on=true]:ring-info/40' },
  { value: 'strong_yes', label: 'Strong yes', icon: <ThumbsUp />, tone: 'data-[on=true]:bg-success/15 data-[on=true]:text-success data-[on=true]:ring-success/40' },
]

function Stars({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  return (
    <div role="radiogroup" aria-label={label} className="flex items-center gap-1">
      {[1, 2, 3, 4, 5].map((n) => (
        <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={`${n} of 5`} onClick={() => onChange(value === n ? 0 : n)}
          className="rounded-md p-0.5 transition outline-none hover:scale-110 focus-visible:ring-2 focus-visible:ring-ring">
          <Star className={cn('size-6 transition', n <= value ? 'fill-amber-400 text-amber-400' : 'text-muted-foreground/40')} />
        </button>
      ))}
      <span className="ml-2 w-28 text-xs text-muted-foreground">{SCALE[value] || 'Not rated'}</span>
    </div>
  )
}

/** Structured feedback per interview. Only panelists can submit; the server enforces it. */
export function ScorecardPage() {
  const { id = '' } = useParams()
  const interview = useApiV1InterviewsRetrieve(id)
  const submit = useApiV1InterviewsScorecardsCreate()
  const [ratings, setRatings] = useState<Record<string, number>>({})
  const [recommendation, setRecommendation] = useState<RecommendationEnum | ''>('')
  const [strengths, setStrengths] = useState('')
  const [concerns, setConcerns] = useState('')
  if (interview.isLoading) return <PageSkeleton />
  if (!interview.data) return <ErrorState error={interview.error} />
  const i = interview.data
  return (
    <>
      <DetailHero crumbs={[{ label: 'Interviews', to: '/interviews' }, { label: i.candidate_name }, { label: 'Scorecard' }]}
        avatar={<PersonAvatar name={i.candidate_name} size={64} />} eyebrow={`Scorecard · ${i.requisition_title}`} title={i.candidate_name}
        badges={<StatusBadge value={i.status} />} subtitle={i.title}
        meta={[
          { icon: <CalendarDays />, label: 'When', value: shortDate(i.scheduled_start) },
          { icon: <Hash />, label: 'Round', value: i.round },
          { icon: <Timer />, label: 'Length', value: `${i.duration_minutes} min` },
          { icon: <UserRound />, label: 'Panel', value: `${i.panel_user_ids.length} ${i.panel_user_ids.length === 1 ? 'person' : 'people'}` },
        ]} />
      {submit.isSuccess ? (
        <Panel><SuccessState title="Scorecard saved">The hiring panel can see it now. The feedback agent summarises all scorecards when asked.</SuccessState></Panel>
      ) : (
        <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <Panel title="Your assessment" icon={<ClipboardPen />} description="Rate only what you observed in this interview.">
            <ErrorAlert error={submit.error} />
            <ul className="divide-y divide-border/70">
              {CRITERIA.map((c) => (
                <li key={c} className="flex flex-col gap-2 py-3.5 sm:flex-row sm:items-center">
                  <span className="flex-1 text-[15px] font-medium">{c}</span>
                  <Stars label={c} value={ratings[c] ?? 0} onChange={(v) => setRatings({ ...ratings, [c]: v })} />
                </li>
              ))}
            </ul>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div className="grid gap-1.5"><Label htmlFor="strengths">Strengths</Label><Textarea id="strengths" rows={4} value={strengths} onChange={(e) => setStrengths(e.target.value)} placeholder="What did they show you?" /></div>
              <div className="grid gap-1.5"><Label htmlFor="concerns">Concerns</Label><Textarea id="concerns" rows={4} value={concerns} onChange={(e) => setConcerns(e.target.value)} placeholder="What would you want to probe further?" /></div>
            </div>
            <fieldset className="mt-5">
              <legend className="mb-2 text-sm font-medium">Recommendation</legend>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {RECOMMENDATIONS.map((r) => (
                  <button key={r.value} type="button" data-on={recommendation === r.value} aria-pressed={recommendation === r.value} onClick={() => setRecommendation(r.value)}
                    className={cn('flex flex-col items-center gap-1.5 rounded-xl border bg-muted/30 px-3 py-3 text-sm font-semibold ring-1 ring-transparent transition ring-inset hover:bg-accent [&_svg]:size-5', r.tone)}>
                    {r.icon}{r.label}
                  </button>
                ))}
              </div>
            </fieldset>
            <div className="mt-6 flex justify-end border-t pt-4">
              <Button size="lg" disabled={!recommendation || submit.isPending}
                onClick={() => recommendation && submit.mutate({ id, data: {
                  recommendation, strengths, concerns, ratings: Object.fromEntries(Object.entries(ratings).filter(([, v]) => v > 0)),
                } })}><CheckCircle2 /> Submit scorecard</Button>
            </div>
          </Panel>
          <Panel title="Keep it fair" icon={<ShieldAlert />}>
            <ul className="space-y-3 text-[13px] leading-relaxed text-muted-foreground">
              <li>Write about the work: what they explained, built or reasoned through.</li>
              <li>Do not comment on age, gender, family, accent, appearance or anything else unrelated to the job.</li>
              <li>Submit before you read other panelists' scorecards, so your view stays your own.</li>
              <li>Your scorecard is stored with your name and can be audited.</li>
            </ul>
          </Panel>
        </div>
      )}
    </>
  )
}
