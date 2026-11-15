import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { toast } from 'sonner'
import {
  Bot, Briefcase, CalendarDays, CheckCircle2, ClipboardCheck, FileText, FileUp, KanbanSquare, Lightbulb, MapPin, Pencil, Play, Search,
  Send, UserRound, Users, XCircle,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { DataTable } from '@/components/app/data-table'
import { DetailHero, FactList } from '@/components/app/detail'
import { ReasonDialog } from '@/components/app/dialogs'
import { Panel, Tag } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import { RunProgress } from '@/components/app/run-progress'
import { EmptyState, ErrorAlert, ErrorState, PageSkeleton } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { Stages } from '@/components/app/timeline'
import { useSession } from '@/app/session'
import { useApiV1AgentRunsList } from '@/shared/api/generated/agent-runs/agent-runs'
import { useApiV1MembersList } from '@/shared/api/generated/auth/auth'
import type { AgentRun, Application } from '@/shared/api/generated/model'
import {
  useApiV1RequisitionsApplicationsList, useApiV1RequisitionsCloseCreate, useApiV1RequisitionsImportApplicantsCreate,
  useApiV1RequisitionsMatchRunsCreate, useApiV1RequisitionsPartialUpdate, useApiV1RequisitionsRetrieve,
  useApiV1RequisitionsReviewRunsCreate, useApiV1RequisitionsSourcingRunsCreate, useApiV1RequisitionsSubmitCreate,
} from '@/shared/api/generated/requisitions/requisitions'
import { useMe } from '@/shared/hooks/useMe'
import { useRunEvents } from '@/shared/hooks/useRunEvents'
import { relativeTime, shortDate } from '@/shared/ui/common'
import { RequisitionForm, type RequisitionValues } from './RequisitionForm'

type Suggestion = { field: string; issue: string; suggestion: string }

function ReviewResult({ runId }: { runId: string }) {
  const { run } = useRunEvents(runId)
  const result = (run?.output as { result?: { issues?: Suggestion[]; suggestions?: Suggestion[]; ready_to_submit?: boolean } })?.result
  if (!result) return <RunProgress runId={runId} title="Requisition review" />
  const items = result.suggestions?.length ? result.suggestions : result.issues ?? []
  return (
    <Panel title="Requisition agent's review" icon={<Lightbulb />} description={result.ready_to_submit ? 'Nothing missing. Ready to submit.' : `${items.length} suggestion${items.length === 1 ? '' : 's'} before you submit`}>
      {result.ready_to_submit ? <p className="flex items-center gap-2 text-sm text-success"><CheckCircle2 className="size-4" /> Looks complete.</p> : (
        <ul className="space-y-2.5">
          {items.map((s) => (
            <li key={s.field + s.issue} className="rounded-xl border bg-muted/40 p-3">
              <p className="text-sm font-semibold capitalize">{s.field.replaceAll('_', ' ')}: <span className="font-normal normal-case">{s.issue}</span></p>
              <p className="mt-1 text-[13px] text-muted-foreground">{s.suggestion}</p>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  )
}

function SourcingResult({ runId }: { runId: string }) {
  const { run } = useRunEvents(runId)
  const result = (run?.output as { result?: { applicants?: unknown[]; talent_pool?: { candidate_id: string; score: number }[] } })?.result
  if (!result) return <RunProgress runId={runId} title="Candidate sourcing" />
  return (
    <Panel title="Sourcing" icon={<Search />} description={`${result.applicants?.length ?? 0} applicants · ${(result.talent_pool ?? []).length} consented talent-pool matches`}>
      <ul className="-mx-2">
        {(result.talent_pool ?? []).map((c) => (
          <li key={c.candidate_id}>
            <Link to={`/candidates/${c.candidate_id}`} className="flex items-center gap-3 rounded-xl px-2 py-2 hover:bg-accent">
              <PersonAvatar name={c.candidate_id} size={30} />
              <span className="flex-1 text-sm font-medium">Talent pool candidate {c.candidate_id.slice(0, 6)}</span>
              <span className="text-xs text-muted-foreground">open profile →</span>
            </Link>
          </li>
        ))}
      </ul>
    </Panel>
  )
}

function Applicants({ rows, loading }: { rows: Application[] | undefined; loading: boolean }) {
  const navigate = useNavigate()
  const blind = useSession((s) => s.blindReview)
  return (
    <Panel flush className="overflow-hidden">
      <DataTable rows={rows} rowKey={(a) => a.id} loading={loading} onOpen={(a) => navigate(`/candidates/${a.candidate_id}`)}
        filterText={(a) => `${a.candidate_name} ${a.stage} ${a.source}`} filterPlaceholder="Search applicants" exportName="applicants"
        initialSort={{ key: 'applied', desc: true }}
        facets={[{ key: 'stage', label: 'Stage', value: (a) => a.stage }, { key: 'source', label: 'Source', value: (a) => a.source || null }]}
        empty={<EmptyState icon={<Users />} title="No applicants yet">Import a CSV, add candidates, or source from the talent pool.</EmptyState>}
        columns={[
          { key: 'name', header: 'Candidate', sort: (a: Application) => a.candidate_name, cell: (a: Application) => (
            <div className="flex items-center gap-3">
              <PersonAvatar name={blind ? a.id : a.candidate_name} size={34} />
              <span className="font-semibold">{blind ? `Candidate ${a.id.slice(0, 4).toUpperCase()}` : a.candidate_name}</span>
            </div>
          ) },
          { key: 'stage', header: 'Stage', sort: (a: Application) => a.stage, cell: (a: Application) => <StatusBadge value={a.stage} /> },
          { key: 'source', header: 'Source', hide: 'sm', sort: (a: Application) => a.source ?? '', cell: (a: Application) => <Tag className="capitalize">{(a.source || 'applied').replaceAll('_', ' ')}</Tag> },
          { key: 'moved', header: 'In stage since', hide: 'md', sort: (a: Application) => a.stage_changed_at ?? a.created_at, cell: (a: Application) => <span className="text-muted-foreground">{relativeTime(a.stage_changed_at ?? a.created_at)}</span> },
          { key: 'applied', header: 'Applied', hide: 'lg', sort: (a: Application) => a.created_at, cell: (a: Application) => <span className="text-muted-foreground">{shortDate(a.created_at)}</span> },
        ]} />
    </Panel>
  )
}

export function RequisitionDetailPage() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { hasRole } = useMe()
  const requisition = useApiV1RequisitionsRetrieve(id)
  const runs = useApiV1AgentRunsList({ requisition: id })
  const applicants = useApiV1RequisitionsApplicationsList(id)
  const members = useApiV1MembersList()
  const update = useApiV1RequisitionsPartialUpdate()
  const submit = useApiV1RequisitionsSubmitCreate()
  const close = useApiV1RequisitionsCloseCreate()
  const review = useApiV1RequisitionsReviewRunsCreate()
  const match = useApiV1RequisitionsMatchRunsCreate()
  const sourcing = useApiV1RequisitionsSourcingRunsCreate()
  const importCsv = useApiV1RequisitionsImportApplicantsCreate()
  const [editing, setEditing] = useState(false)
  const [closing, setClosing] = useState(false)
  const [csvOpen, setCsvOpen] = useState(false)
  const [csv, setCsv] = useState('full_name,email,phone,consent,talent_pool\n')
  const [reviewRun, setReviewRun] = useState<string | null>(null)
  const [sourcingRun, setSourcingRun] = useState<string | null>(null)

  if (requisition.isLoading) return <PageSkeleton />
  if (!requisition.data) return <ErrorState error={requisition.error} />
  const r = requisition.data
  const editable = r.status === 'draft' || r.status === 'rejected'
  const recruiter = hasRole('hr_admin', 'recruiter')
  const latestMatch = runs.data?.results?.find((run) => run.kind === 'matching')
  const stage = r.status === 'draft' ? 0 : r.status === 'submitted' || r.status === 'rejected' ? 1 : !latestMatch ? 2 : latestMatch.status === 'awaiting_review' ? 3 : 4
  const manager = members.data?.find((m) => m.user_id === r.hiring_manager_id)?.full_name ?? '—'
  const byStage = (s: string) => (applicants.data ?? []).filter((a) => a.stage === s).length

  return (
    <>
      <DetailHero crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Jobs', to: '/requisitions' }, { label: r.title }]}
        avatar={<span className="bg-brand grid size-14 place-items-center rounded-xl text-white"><Briefcase className="size-7" /></span>}
        eyebrow={`Job · ${r.department}`} title={r.title} badges={<StatusBadge value={r.status} />}
        subtitle={<span className="flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="flex items-center gap-1.5"><MapPin className="size-4" />{r.location || 'Location to be confirmed'}</span>
          <span>{r.level || 'No level'} · <span className="capitalize">{(r.employment_type ?? '').replaceAll('_', ' ')}</span></span>
        </span>}
        actions={<>
          <Button variant="outline" asChild><Link to={`/requisitions/${id}/jd`}><FileText /> JD studio</Link></Button>
          <Button variant="outline" asChild><Link to={`/requisitions/${id}/pipeline`}><KanbanSquare /> Pipeline</Link></Button>
          <Button variant="outline" asChild><Link to={`/requisitions/${id}/review`}><ClipboardCheck /> Screening</Link></Button>
          {r.status === 'draft' && <Button onClick={() => submit.mutate({ id }, { onSuccess: () => toast.success('Submitted for HR approval') })}><Send /> Submit for approval</Button>}
          {r.status === 'approved' && recruiter && <Button disabled={match.isPending} onClick={() => match.mutate({ id, data: {} }, { onSuccess: () => toast.success('Matching started') })}><Play /> Run matching</Button>}
        </>}
        meta={[
          { icon: <Users />, label: 'Openings', value: r.headcount },
          { icon: <UserRound />, label: 'Hiring manager', value: manager },
          { icon: <ClipboardCheck />, label: 'Applicants', value: `${applicants.data?.length ?? 0} · ${byStage('shortlisted')} shortlisted` },
          { icon: <CalendarDays />, label: r.approved_at ? 'Approved' : 'Created', value: shortDate(r.approved_at ?? r.created_at) },
        ]}>
        <Stages steps={['Draft', 'HR approval', 'Match candidates', 'Shortlist review', 'Interviews & offers']} active={r.status === 'closed' ? 5 : stage} failed={r.status === 'rejected'} />
      </DetailHero>
      <ErrorAlert error={submit.error ?? update.error ?? match.error ?? review.error ?? close.error ?? sourcing.error} />

      <Tabs defaultValue="overview">
        <TabsList className="mb-4">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="applicants">Applicants ({applicants.data?.length ?? 0})</TabsTrigger>
          <TabsTrigger value="runs">Agent runs ({runs.data?.count ?? 0})</TabsTrigger>
        </TabsList>
        <TabsContent value="overview">
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
            <div className="space-y-6">
              {editing ? (
                <Panel title="Edit job" icon={<Pencil />}>
                  <RequisitionForm submitLabel="Save changes" busy={update.isPending} onCancel={() => setEditing(false)}
                    onSubmit={(values: RequisitionValues) => update.mutate({ id, data: values }, { onSuccess: () => { setEditing(false); toast.success('Saved') } })}
                    initial={{
                      title: r.title, department: r.department, location: r.location ?? '', level: r.level ?? '',
                      employment_type: (r.employment_type ?? 'full_time') as RequisitionValues['employment_type'],
                      headcount: r.headcount ?? 1, summary: r.summary ?? '', must_have_skills: [...(r.must_have_skills ?? [])],
                      nice_to_have_skills: [...(r.nice_to_have_skills ?? [])], comp_band_id: r.comp_band_id ?? null, hiring_manager_id: r.hiring_manager_id,
                    }} />
                </Panel>
              ) : (
                <Panel title="About this role" icon={<Briefcase />} action={editable && <Button variant="outline" size="sm" onClick={() => setEditing(true)}><Pencil /> Edit</Button>}>
                  <p className="text-[15px] leading-relaxed text-foreground/90">{r.summary || <span className="text-muted-foreground italic">No business need written yet.</span>}</p>
                  <div className="mt-5 grid gap-5 sm:grid-cols-2">
                    <div>
                      <p className="mb-2 text-xs font-bold tracking-wide text-muted-foreground uppercase">Must have</p>
                      <div className="flex flex-wrap gap-1.5">{(r.must_have_skills ?? []).map((s) => <Tag key={s} tone="violet">{s}</Tag>)}
                        {(r.must_have_skills ?? []).length === 0 && <span className="text-sm text-muted-foreground">None listed</span>}</div>
                    </div>
                    <div>
                      <p className="mb-2 text-xs font-bold tracking-wide text-muted-foreground uppercase">Nice to have</p>
                      <div className="flex flex-wrap gap-1.5">{(r.nice_to_have_skills ?? []).map((s) => <Tag key={s}>{s}</Tag>)}
                        {(r.nice_to_have_skills ?? []).length === 0 && <span className="text-sm text-muted-foreground">None listed</span>}</div>
                    </div>
                  </div>
                </Panel>
              )}
              <Panel title="Next steps" icon={<Bot />} description="Agents draft and recommend. Nothing reaches a candidate until a person approves it.">
                <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
                  {editable && <Button variant="outline" className="justify-start" onClick={() => review.mutate({ id, data: {} }, { onSuccess: (run) => setReviewRun(run.id) })}><Lightbulb /> Check with the requisition agent</Button>}
                  {r.status === 'approved' && recruiter && <Button variant="outline" className="justify-start" onClick={() => sourcing.mutate({ id, data: {} }, { onSuccess: (run) => setSourcingRun(run.id) })}><Search /> Source candidates</Button>}
                  {r.status === 'approved' && recruiter && <Button variant="outline" className="justify-start" onClick={() => setCsvOpen(true)}><FileUp /> Import applicants (CSV)</Button>}
                  <Button variant="outline" className="justify-start" asChild><Link to={`/requisitions/${id}/jd`}><FileText /> Draft or edit the JD</Link></Button>
                  {r.status !== 'closed' && hasRole('hr_admin', 'hiring_manager') && <Button variant="destructive" className="justify-start" onClick={() => setClosing(true)}><XCircle /> Close this job</Button>}
                </div>
              </Panel>
            </div>
            <div className="space-y-6">
              {reviewRun && <ReviewResult runId={reviewRun} />}
              {sourcingRun && <SourcingResult runId={sourcingRun} />}
              {(match.data?.id ?? latestMatch?.id) && <RunProgress runId={(match.data?.id ?? latestMatch?.id) as string} title="Latest matching run" />}
              <Panel title="Applicants by stage" icon={<Users />}>
                <FactList items={['applied', 'screening', 'shortlisted', 'interview', 'offer', 'hired', 'rejected'].map((s) => ({
                  icon: <span className="block size-2 rounded-full bg-violet" />, label: s[0].toUpperCase() + s.slice(1), value: <span className="tabular">{byStage(s)}</span>,
                }))} />
              </Panel>
              <Panel title="Record" icon={<CalendarDays />}>
                <FactList items={[
                  { icon: <CalendarDays />, label: 'Created', value: shortDate(r.created_at) },
                  { icon: <Send />, label: 'Submitted', value: shortDate(r.submitted_at) },
                  { icon: <CheckCircle2 />, label: 'Approved', value: shortDate(r.approved_at) },
                  { icon: <UserRound />, label: 'Recruiters assigned', value: (r.assigned_recruiter_ids ?? []).length },
                ]} />
              </Panel>
            </div>
          </div>
        </TabsContent>
        <TabsContent value="applicants"><Applicants rows={applicants.data} loading={applicants.isLoading} /></TabsContent>
        <TabsContent value="runs">
          <Panel flush className="overflow-hidden">
            <DataTable rows={runs.data?.results} rowKey={(run) => run.id} loading={runs.isLoading} onOpen={(run) => navigate(`/agents/${run.id}`)}
              initialSort={{ key: 'when', desc: true }} facets={[{ key: 'kind', label: 'Agent', value: (run) => run.kind }, { key: 'status', label: 'Status', value: (run) => run.status }]}
              empty={<EmptyState icon={<Bot />} title="No agent runs yet">Runs start when you check the job, draft a JD or run matching.</EmptyState>}
              columns={[
                { key: 'kind', header: 'Agent', sort: (run: AgentRun) => run.kind, cell: (run: AgentRun) => <span className="flex items-center gap-2.5 font-semibold capitalize"><Bot className="size-4 text-violet" />{run.kind.replaceAll('_', ' ')}</span> },
                { key: 'status', header: 'Status', sort: (run: AgentRun) => run.status, cell: (run: AgentRun) => <StatusBadge value={run.status} /> },
                { key: 'tools', header: 'Tool calls', align: 'right', sort: (run: AgentRun) => run.tool_call_count, cell: (run: AgentRun) => <span className="tabular">{run.tool_call_count}</span> },
                { key: 'tokens', header: 'Tokens', align: 'right', hide: 'md', sort: (run: AgentRun) => run.tokens_in + run.tokens_out, cell: (run: AgentRun) => <span className="tabular">{(run.tokens_in + run.tokens_out).toLocaleString()}</span> },
                { key: 'when', header: 'Started', sort: (run: AgentRun) => run.created_at, cell: (run: AgentRun) => <span className="text-muted-foreground">{relativeTime(run.created_at)}</span> },
              ]} />
          </Panel>
        </TabsContent>
      </Tabs>

      <ReasonDialog open={closing} title="Close this job" destructive confirmLabel="Close job" onClose={() => setClosing(false)}
        onConfirm={(reason) => close.mutate({ id, data: { reason } }, { onSuccess: () => { setClosing(false); toast.success('Job closed') } })} />
      <Dialog open={csvOpen} onOpenChange={setCsvOpen}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">Import applicants</DialogTitle>
            <DialogDescription>One person per line. Rows without consent=yes are skipped: we do not store people who did not agree.</DialogDescription>
          </DialogHeader>
          <Textarea value={csv} onChange={(e) => setCsv(e.target.value)} rows={8} className="font-mono text-[13px]" aria-label="CSV" />
          {importCsv.data && <p className="rounded-xl bg-success/10 px-3 py-2.5 text-sm text-success">Created {importCsv.data.created}, already there {importCsv.data.existing}, skipped without consent {importCsv.data.skipped_no_consent}.</p>}
          <ErrorAlert error={importCsv.error} />
          <DialogFooter>
            <Button variant="ghost" onClick={() => setCsvOpen(false)}>Close</Button>
            <Button disabled={importCsv.isPending} onClick={() => importCsv.mutate({ id, data: { csv } })}><FileUp /> Import</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
