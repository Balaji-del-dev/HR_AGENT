import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import { motion } from 'motion/react'
import { ArrowRightCircle, EyeOff, GitCompareArrows, PauseCircle, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { ReasonDialog } from '@/components/app/dialogs'
import { PageHeader, Panel } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import { EmptyState, ErrorAlert, PageSkeleton } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { useSession } from '@/app/session'
import { useApiV1ApplicationsDecisionsCreate } from '@/shared/api/generated/applications/applications'
import { useApiV1ApprovalsList } from '@/shared/api/generated/approvals/approvals'
import { useApiV1CandidatesRetrieve } from '@/shared/api/generated/candidates/candidates'
import type { Assessment, RecruiterDecisionEnum } from '@/shared/api/generated/model'
import {
  useApiV1RequisitionsApplicationsList, useApiV1RequisitionsAssessmentsList, useApiV1RequisitionsRetrieve,
} from '@/shared/api/generated/requisitions/requisitions'
import { useMe } from '@/shared/hooks/useMe'
import { shortDate } from '@/shared/ui/common'
import { CriteriaMatrix } from './CriteriaMatrix'
import { ResumeViewer } from './ResumeViewer'

type Summary = { documented?: number; not_documented?: number; unclear?: number; mandatory_gaps?: string[] }

/** Documented / not documented / unclear as a strip of equal cells: a coverage picture, never a score. */
function Coverage({ assessment }: { assessment: Assessment }) {
  return (
    <span className="flex gap-0.5" aria-label="Criteria coverage">
      {assessment.criteria.map((c) => (
        <span key={c.id} title={`${c.criterion}: ${c.status.replaceAll('_', ' ')}`}
          className={cn('h-1.5 w-3 rounded-full', c.status === 'documented' ? 'bg-success' : c.status === 'unclear' ? 'bg-warning' : 'bg-border')} />
      ))}
    </span>
  )
}

function Review({ assessment, label }: { assessment: Assessment; label: string }) {
  const { hasRole } = useMe()
  const blind = useSession((s) => s.blindReview)
  const candidate = useApiV1CandidatesRetrieve(assessment.candidate_id)
  const decide = useApiV1ApplicationsDecisionsCreate()
  const [focus, setFocus] = useState<string | null>(null)
  const [decision, setDecision] = useState<RecruiterDecisionEnum | null>(null)
  const highlighted = useMemo(() => new Set(assessment.criteria.flatMap((c) => ((c.evidence ?? []) as { span_id: string }[]).map((e) => e.span_id))), [assessment])
  const doc = candidate.data?.documents?.find((d) => d.status === 'processed')
  const summary = assessment.summary as Summary

  return (
    <div className="grid grid-cols-1 gap-6 2xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <Panel title={label} description={`${summary.documented ?? 0} documented · ${summary.not_documented ?? 0} not documented · ${summary.unclear ?? 0} unclear`}
        action={<Coverage assessment={assessment} />}>
        {(summary.mandatory_gaps ?? []).length > 0 && (
          <p className="mb-2 rounded-xl bg-warning/10 px-3 py-2.5 text-[13px] leading-relaxed">
            No evidence yet for <strong>{summary.mandatory_gaps?.join(', ')}</strong>. Ask before deciding: a gap in the resume is not a gap in ability.
          </p>
        )}
        <CriteriaMatrix criteria={assessment.criteria} onFocus={setFocus} active={focus} />
        <p className="mt-3 font-mono text-xs text-muted-foreground">JD v{assessment.job_description_version} · {assessment.prompt_version} · {assessment.model_name} · {shortDate(assessment.created_at)}</p>
        {hasRole('hr_admin', 'recruiter', 'hiring_manager') && (
          <div className="mt-4 flex flex-wrap gap-2 border-t pt-4">
            <Button onClick={() => setDecision('advance')}><ArrowRightCircle /> Advance</Button>
            <Button variant="outline" onClick={() => setDecision('hold')}><PauseCircle /> Hold</Button>
            <Button variant="ghost" className="text-destructive hover:text-destructive" onClick={() => setDecision('reject')}><XCircle /> Reject</Button>
          </div>
        )}
        <ErrorAlert error={decide.error} />
      </Panel>
      <div className="2xl:sticky 2xl:top-20 2xl:self-start">
        {doc ? <ResumeViewer documentId={doc.id} highlighted={highlighted} focus={focus} blind={blind} /> : <Panel><EmptyState>No processed resume.</EmptyState></Panel>}
      </div>
      <ReasonDialog open={Boolean(decision)} title={`${decision === 'advance' ? 'Advance' : decision === 'hold' ? 'Hold' : 'Reject'} ${label}`}
        description="Your reason is stored with the decision and the evidence you saw." destructive={decision === 'reject'}
        confirmLabel={decision === 'advance' ? 'Advance' : decision === 'hold' ? 'Hold' : 'Reject'} onClose={() => setDecision(null)}
        onConfirm={(reason) => decision && decide.mutate({ id: assessment.application_id, data: { decision, reason, assessment_id: assessment.id } },
          { onSuccess: () => toast.success('Decision recorded'), onSettled: () => setDecision(null) })} />
    </div>
  )
}

export function CandidateReviewPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { blindReview, setBlindReview } = useSession()
  const requisition = useApiV1RequisitionsRetrieve(id)
  const assessments = useApiV1RequisitionsAssessmentsList(id)
  const applications = useApiV1RequisitionsApplicationsList(id)
  const shortlist = useApiV1ApprovalsList({ requisition: id, kind: 'shortlist_review', status: 'pending' })
  const [selected, setSelected] = useState<string | null>(null)
  const list = assessments.data ?? []
  const current = list.find((a) => a.id === selected) ?? list[0]
  const nameOf = (a: Assessment, i: number) => blindReview ? `Candidate ${i + 1}` : applications.data?.find((x) => x.id === a.application_id)?.candidate_name ?? `Candidate ${i + 1}`
  const stageOf = (a: Assessment) => applications.data?.find((x) => x.id === a.application_id)?.stage

  if (assessments.isLoading) return <PageSkeleton />
  return (
    <>
      <PageHeader crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Jobs', to: '/requisitions' }, { label: requisition.data?.title ?? 'Job', to: `/requisitions/${id}` }, { label: 'Screening' }]}
        title="Resume screening" description="Each requirement is checked against the resume. Click a quote to see it marked on the page."
        actions={<>
          <label className="flex items-center gap-2 glass rounded-xl px-3 py-1.5 text-sm"><EyeOff className="size-4 text-muted-foreground" /> Blind review
            <Switch checked={blindReview} onCheckedChange={setBlindReview} aria-label="Blind review" /></label>
          {list.length >= 2 && <Button variant="outline" onClick={() => navigate(`/candidates/compare?ids=${list.slice(0, 3).map((a) => a.candidate_id).join(',')}&job=${id}`)}><GitCompareArrows /> Compare</Button>}
          {shortlist.data?.results?.[0] && <Button asChild><Link to={`/approvals/${shortlist.data.results[0].id}`}>Finish shortlist review</Link></Button>}
        </>} />
      <ErrorAlert error={assessments.error} />
      {list.length === 0 ? <Panel><EmptyState title="Nothing screened yet">Run matching from the job page; each applicant gets a criteria-by-criteria check.</EmptyState></Panel> : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-[260px_minmax(0,1fr)]">
          <nav aria-label="Candidates" className="space-y-1.5 lg:sticky lg:top-20 lg:self-start">
            {list.map((a, i) => (
              <motion.button key={a.id} type="button" onClick={() => setSelected(a.id)} initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }}
                className={cn('flex w-full items-center gap-3 glass rounded-xl p-3 text-left transition hover:border-primary/30', current?.id === a.id && 'border-primary/40 ring-2 ring-primary/15')}>
                <PersonAvatar name={blindReview ? a.id : nameOf(a, i)} size={36} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{nameOf(a, i)}</span>
                  <span className="mt-1 block"><Coverage assessment={a} /></span>
                </span>
                <StatusBadge value={stageOf(a)} />
              </motion.button>
            ))}
          </nav>
          {current && <Review key={current.id} assessment={current} label={nameOf(current, list.indexOf(current))} />}
        </div>
      )}
    </>
  )
}
