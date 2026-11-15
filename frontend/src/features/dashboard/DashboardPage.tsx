import { Link, useNavigate } from 'react-router'
import { motion } from 'motion/react'
import { ArrowRight, Bot, Briefcase, CalendarCheck, ClipboardCheck, Plus, Sparkles, UserRound, Users, Wallet } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { KIND_ICON, KIND_TINT } from '@/components/app/kinds'
import { Panel } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import { StatTile } from '@/components/app/stat'
import { EmptyState, SkeletonRows } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { useSession } from '@/app/session'
import { useApiV1AgentRunsList } from '@/shared/api/generated/agent-runs/agent-runs'
import { useApiV1AnalyticsPipelineRetrieve } from '@/shared/api/generated/analytics/analytics'
import { useApiV1ApprovalsList } from '@/shared/api/generated/approvals/approvals'
import { useApiV1CandidatesList } from '@/shared/api/generated/candidates/candidates'
import { useApiV1InterviewsList } from '@/shared/api/generated/interviews/interviews'
import { useApiV1OffersList } from '@/shared/api/generated/offers/offers'
import {
  useApiV1RequisitionsApplicationsList, useApiV1RequisitionsAssessmentsList, useApiV1RequisitionsList,
} from '@/shared/api/generated/requisitions/requisitions'
import { useMe } from '@/shared/hooks/useMe'
import { relativeTime, shortDate } from '@/shared/ui/common'

const STAGES = ['applied', 'screening', 'shortlisted', 'interview', 'offer', 'hired']
const RUN_DOT: Record<string, string> = {
  running: 'bg-cyan text-cyan pulse-ring', queued: 'bg-cyan text-cyan pulse-ring', awaiting_review: 'bg-amber-400',
  completed: 'bg-success', failed: 'bg-destructive', budget_exceeded: 'bg-destructive',
}

/** The strongest open job, its applicants and how each one's resume covers the requirements. */
function JobScreening({ jobId, title }: { jobId: string; title: string }) {
  const blind = useSession((s) => s.blindReview)
  const assessments = useApiV1RequisitionsAssessmentsList(jobId)
  const applications = useApiV1RequisitionsApplicationsList(jobId)
  const rows = (assessments.data ?? []).slice(0, 4)
  const app = (id: string) => applications.data?.find((a) => a.id === id)
  return (
    <Panel title={<>Candidates · <span className="text-muted-foreground">{title}</span></>}
      action={<Button variant="ghost" size="sm" asChild><Link to={`/requisitions/${jobId}/review`}>Open screening <ArrowRight /></Link></Button>}>
      {assessments.isLoading ? <SkeletonRows rows={3} /> : rows.length === 0 ? (
        <EmptyState icon={<Users />} title="Not screened yet">Run matching on this job to check each applicant against every requirement.</EmptyState>
      ) : (
        <ul className="divide-y divide-border/70">
          {rows.map((a, i) => {
            const application = app(a.application_id)
            const name = blind ? `Candidate ${i + 1}` : application?.candidate_name ?? `Candidate ${i + 1}`
            return (
              <li key={a.id}>
                <Link to={`/candidates/${a.candidate_id}`} className="-mx-2 flex items-center gap-3 rounded-xl px-2 py-3 transition hover:bg-accent">
                  <PersonAvatar name={blind ? a.id : name} size={40} />
                  <span className="w-44 min-w-0 shrink-0">
                    <span className="block truncate text-sm font-semibold">{name}</span>
                    <span className="block truncate text-xs text-muted-foreground">{a.criteria.filter((c) => c.status === 'documented').length} of {a.criteria.length} documented</span>
                  </span>
                  <span className="hidden min-w-0 flex-1 flex-wrap gap-1.5 lg:flex">
                    {a.criteria.slice(0, 5).map((c) => (
                      <span key={c.id} title={c.status.replaceAll('_', ' ')} className={cn('rounded-md px-2 py-0.5 text-xs font-semibold ring-1 ring-inset',
                        c.status === 'documented' ? 'bg-success/12 text-success ring-success/30' : c.status === 'unclear' ? 'bg-warning/12 text-warning ring-warning/30' : 'bg-foreground/5 text-muted-foreground line-through ring-border')}>
                        {c.criterion}
                      </span>
                    ))}
                  </span>
                  <StatusBadge value={application?.stage} className="ml-auto" />
                </Link>
              </li>
            )
          })}
        </ul>
      )}
    </Panel>
  )
}

export function DashboardPage() {
  const navigate = useNavigate()
  const { me, hasRole } = useMe()
  const recruiting = hasRole('hr_admin', 'recruiter', 'hiring_manager')
  const recruiter = hasRole('hr_admin', 'recruiter')
  const approvals = useApiV1ApprovalsList({ status: 'pending' })
  const jobs = useApiV1RequisitionsList(undefined, { query: { enabled: recruiting } })
  const candidates = useApiV1CandidatesList(undefined, { query: { enabled: recruiting } })
  const talentPool = useApiV1CandidatesList({ in_talent_pool: true }, { query: { enabled: recruiting } })
  const runs = useApiV1AgentRunsList(undefined, { query: { enabled: recruiting, refetchInterval: 10_000 } })
  const interviews = useApiV1InterviewsList(recruiter ? undefined : { mine: true }, { query: { enabled: hasRole('interviewer', 'hiring_manager', 'recruiter', 'hr_admin') } })
  const offers = useApiV1OffersList(undefined, { query: { enabled: hasRole('hr_admin', 'recruiter', 'finance_approver') } })
  const funnel = useApiV1AnalyticsPipelineRetrieve({ report: 'pipeline_funnel' }, { query: { enabled: recruiting } })

  const decidable = approvals.data?.results?.filter((a) => a.can_decide) ?? []
  const openJobs = jobs.data?.results?.filter((r) => r.status === 'approved') ?? []
  const counts = Object.fromEntries((funnel.data?.rows ?? []).map((r) => [String(r[0]), Number(r[1])]))
  const maxStage = Math.max(1, ...STAGES.map((s) => counts[s] ?? 0))
  const weekAhead = Date.now() + 7 * 864e5
  const upcoming = (interviews.data?.results ?? []).filter((i) => i.scheduled_start && new Date(i.scheduled_start).getTime() >= Date.now() - 864e5 && new Date(i.scheduled_start).getTime() <= weekAhead)
  const accepted = (offers.data?.results ?? []).filter((o) => o.status === 'accepted').length
  const offersOpen = (offers.data?.results ?? []).filter((o) => ['draft', 'pending_approval', 'approved', 'sent'].includes(o.status)).length
  const hour = new Date().getHours()
  const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening'
  const first = me?.full_name.split(' ')[0] ?? ''

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 sm:flex-row sm:items-center">
        <div className="flex-1">
          <h1 className="text-2xl leading-8 font-semibold">{greeting}, {first} </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {decidable.length > 0
              ? <><span className="font-semibold text-foreground">{decidable.length} {decidable.length === 1 ? 'decision needs' : 'decisions need'} you</span> today. Agents have prepared the drafts and the evidence.</>
              : 'Nothing is waiting on you. New drafts from agents will appear here.'}
          </p>
        </div>
        {recruiting && <Button onClick={() => navigate('/requisitions?new=1')}><Plus /> Post a new job</Button>}
      </section>

      {recruiting && (
        <section className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
          <StatTile label="Open jobs" value={openJobs.length} icon={<Briefcase />} tone="primary" to="/requisitions" loading={jobs.isLoading}
            hint={`${(jobs.data?.results ?? []).filter((r) => r.status === 'submitted').length} waiting for HR approval`} />
          <StatTile label="Candidates" value={candidates.data?.count ?? 0} icon={<Users />} tone="info" to="/candidates" loading={candidates.isLoading}
            hint={`${talentPool.data?.count ?? 0} in the talent pool`} />
          <StatTile label="Interviews this week" value={upcoming.length} icon={<CalendarCheck />} tone="pink" to="/interviews" loading={interviews.isLoading}
            hint={`${(interviews.data?.results ?? []).filter((i) => i.status === 'proposed').length} waiting for a time`} />
          {hasRole('hr_admin', 'recruiter', 'finance_approver')
            ? <StatTile label="Offers accepted" value={accepted} icon={<Wallet />} tone="success" to="/offers" loading={offers.isLoading} hint={`${offersOpen} offers in progress`} />
            : <StatTile label="Agent runs today" value={(runs.data?.results ?? []).filter((r) => new Date(r.created_at).toDateString() === new Date().toDateString()).length} icon={<Sparkles />} tone="success" to="/agents" />}
        </section>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.05fr)_minmax(0,1fr)]">
        {recruiting && (
          <Panel title="Hiring pipeline" description="Applications on the jobs you can see"
            action={<Button variant="ghost" size="sm" asChild><Link to="/analytics">Analytics <ArrowRight /></Link></Button>}>
            <ul className="space-y-3.5 pt-1">
              {STAGES.map((stage, i) => (
                <li key={stage} className="grid grid-cols-[96px_1fr_44px] items-center gap-4 text-sm">
                  <span className="text-foreground/85 capitalize">{stage}</span>
                  <span className="h-2.5 overflow-hidden rounded-full bg-muted">
                    <motion.span className="block h-full rounded-full bg-primary" initial={{ width: 0 }}
                      animate={{ width: `${Math.max(counts[stage] ? 2 : 0, ((counts[stage] ?? 0) / maxStage) * 100)}%` }} transition={{ duration: 0.8, ease: 'easeOut', delay: 0.15 + i * 0.05 }} />
                  </span>
                  <span className="tabular text-right font-semibold">{counts[stage] ?? 0}</span>
                </li>
              ))}
            </ul>
          </Panel>
        )}

        <Panel title="Waiting for your decision" description="Nothing reaches a candidate until you approve it" action={<Button variant="ghost" size="sm" asChild><Link to="/approvals">View all <ArrowRight /></Link></Button>}
          className={cn(!recruiting && 'xl:col-span-2')}>
          {approvals.isLoading ? <SkeletonRows rows={3} /> : decidable.length === 0 ? (
            <EmptyState title="You're all caught up" icon={<ClipboardCheck />}>New drafts from agents and colleagues will appear here.</EmptyState>
          ) : (
            <ul className="space-y-2.5">
              {decidable.slice(0, 4).map((item, i) => (
                <motion.li key={item.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 + i * 0.06 }}
                  className="flex items-center gap-3.5 rounded-xl border bg-muted/40 p-3">
                  <span className={cn('grid size-10 shrink-0 place-items-center rounded-xl [&_svg]:size-[18px]', KIND_TINT[item.kind] ?? 'bg-primary/15 text-violet')}>{KIND_ICON[item.kind] ?? <ClipboardCheck />}</span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-semibold">{item.title}</p>
                    <p className="flex items-center gap-1.5 truncate text-xs text-muted-foreground">
                      {item.agent_run_id ? <><Bot className="size-3.5" /> Drafted by AI agent</> : <><UserRound className="size-3.5" /> From a colleague</>}
                      <span aria-hidden>·</span>{relativeTime(item.created_at)}
                      {item.chain_length > 1 && <><span aria-hidden>·</span>step {item.step} of {item.chain_length}</>}
                    </p>
                  </div>
                  <Button size="sm" asChild><Link to={`/approvals/${item.id}`}>Review</Link></Button>
                </motion.li>
              ))}
            </ul>
          )}
        </Panel>

        {recruiting && (openJobs[0]
          ? <JobScreening jobId={openJobs[0].id} title={openJobs[0].title} />
          : <Panel title="Candidates" action={<Button variant="ghost" size="sm" asChild><Link to="/requisitions">Jobs <ArrowRight /></Link></Button>}><EmptyState icon={<Briefcase />} title="No open jobs">Approved jobs and their applicants appear here.</EmptyState></Panel>)}

        {recruiting && (
          <Panel title="AI agents" action={<Button variant="ghost" size="sm" asChild><Link to="/agents">Monitor <ArrowRight /></Link></Button>}>
            {runs.isLoading ? <SkeletonRows rows={4} /> : (runs.data?.results ?? []).length === 0 ? (
              <EmptyState icon={<Bot />} title="No agent runs yet">Draft a JD, run matching or ask the AI recruiter to start one.</EmptyState>
            ) : (
              <ul className="-mx-2">
                {(runs.data?.results ?? []).slice(0, 5).map((run) => (
                  <li key={run.id}>
                    <Link to={`/agents/${run.id}`} className="flex items-center gap-3.5 rounded-xl px-2 py-2.5 transition hover:bg-accent">
                      <span className={cn('ml-1 size-2.5 shrink-0 rounded-full', RUN_DOT[run.status] ?? 'bg-muted-foreground')} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-semibold capitalize">{run.kind.replaceAll('_', ' ')}</span>
                        <span className="block text-xs text-muted-foreground tabular">{run.tool_call_count} tool calls · {(run.tokens_in + run.tokens_out).toLocaleString()} tokens · {relativeTime(run.created_at)}</span>
                      </span>
                      <StatusBadge value={run.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        )}

        {hasRole('interviewer') && !recruiting && (
          <Panel title="My interviews" action={<Button variant="ghost" size="sm" asChild><Link to="/interviews">All <ArrowRight /></Link></Button>} className="xl:col-span-2">
            {(interviews.data?.results ?? []).length === 0 ? <EmptyState icon={<CalendarCheck />}>No interviews assigned to you.</EmptyState> : (
              <ul className="-mx-2">
                {interviews.data?.results?.map((i) => (
                  <li key={i.id}>
                    <Link to={`/interviews/${i.id}/scorecard`} className="flex items-center gap-3 rounded-xl px-2 py-2.5 hover:bg-accent">
                      <PersonAvatar name={i.candidate_name} size={36} />
                      <span className="min-w-0 flex-1"><span className="block truncate text-sm font-semibold">{i.candidate_name}</span>
                        <span className="block text-xs text-muted-foreground">{i.title} · {i.requisition_title} · {shortDate(i.scheduled_start)}</span></span>
                      <StatusBadge value={i.status} />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        )}
      </div>
    </div>
  )
}
