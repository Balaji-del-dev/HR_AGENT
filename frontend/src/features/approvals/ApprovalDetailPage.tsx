import { useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'
import { Bot, CalendarDays, CheckCircle2, ClipboardCheck, History, Info, MessageSquareWarning, RotateCcw, UserRound, Users, XCircle } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { DetailHero } from '@/components/app/detail'
import { ReasonDialog } from '@/components/app/dialogs'
import { KIND_ICON, KIND_LABEL, KIND_TINT } from '@/components/app/kinds'
import { KeyValue, Panel } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import { ErrorAlert, ErrorState, PageSkeleton } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { Stages, Timeline } from '@/components/app/timeline'
import { useSession } from '@/app/session'
import { useApiV1ApprovalsDecideCreate, useApiV1ApprovalsRetrieve } from '@/shared/api/generated/approvals/approvals'
import type { ApprovalDecisionEnum, ApprovalRequest } from '@/shared/api/generated/model'
import { useApiV1RequisitionsApplicationsList } from '@/shared/api/generated/requisitions/requisitions'
import { money, shortDate } from '@/shared/ui/common'
import { JdPreview, LanguageFlags, RequirementChips } from '../jd-studio/JdStudioPage'

type Edits = Record<string, unknown>
type Payload = Record<string, unknown>

function Note({ children, tone = 'info' }: { children: ReactNode; tone?: 'info' | 'warning' }) {
  return (
    <p className={cn('flex gap-2.5 rounded-xl px-3.5 py-2.5 text-[13px] ring-1 ring-inset', tone === 'info' ? 'bg-info/8 text-foreground/85 ring-info/25' : 'bg-warning/10 ring-warning/30')}>
      <Info className={cn('mt-0.5 size-4 shrink-0', tone === 'info' ? 'text-info' : 'text-warning')} />{children}
    </p>
  )
}

/** Each review type gets its own editor; all of them post approve / request changes / reject with a reason. */
function useEditor(request: ApprovalRequest): { view: ReactNode; edits: () => Edits; canApprove: boolean; after: string } {
  const payload = request.payload as Payload
  const [subject, setSubject] = useState(String(payload.subject ?? ''))
  const [body, setBody] = useState(String(payload.body ?? ''))
  const [summary, setSummary] = useState(String(payload.summary ?? ''))
  const [slot, setSlot] = useState(String(payload.recommended_slot_id ?? ''))
  const [choices, setChoices] = useState<Record<string, { decision: string; reason: string }>>({})
  const blind = useSession((s) => s.blindReview)
  const applications = useApiV1RequisitionsApplicationsList(request.requisition_id ?? '', undefined, {
    query: { enabled: request.kind === 'shortlist_review' && Boolean(request.requisition_id) },
  })

  switch (request.kind) {
    case 'job_description':
      return {
        canApprove: true, edits: () => ({ body, summary }),
        after: 'The JD is published to the job and its requirement rows are built for matching.',
        view: (
          <div className="space-y-4">
            <LanguageFlags flags={(payload.compliance_flags ?? []) as never[]} />
            <RequirementChips requirements={(payload.requirements ?? []) as never[]} />
            <div className="grid gap-1.5"><Label htmlFor="jd-summary">Summary</Label><Textarea id="jd-summary" rows={2} value={summary} onChange={(e) => setSummary(e.target.value)} /></div>
            <Tabs defaultValue="preview">
              <TabsList><TabsTrigger value="preview">Preview</TabsTrigger><TabsTrigger value="edit">Edit</TabsTrigger></TabsList>
              <TabsContent value="preview" className="mt-3 rounded-xl border bg-muted/30 p-6"><JdPreview body={body} /></TabsContent>
              <TabsContent value="edit" className="mt-3"><Textarea rows={18} value={body} onChange={(e) => setBody(e.target.value)} className="font-mono text-[13px]" aria-label="JD markdown" /></TabsContent>
            </Tabs>
          </div>
        ),
      }
    case 'email':
      return {
        canApprove: Boolean(subject && body), edits: () => ({ subject, body }),
        after: 'The email is sent exactly once, to the address on the candidate record.',
        view: (
          <div className="space-y-4">
            <div className="flex items-center gap-3 rounded-xl border bg-muted/40 px-3.5 py-2.5 text-sm">
              <span className="text-muted-foreground">To</span><PersonAvatar name={String(payload.to ?? '?')} size={24} /><span className="font-medium">{String(payload.to ?? '')}</span>
            </div>
            <div className="grid gap-1.5"><Label htmlFor="mail-subject">Subject</Label><Input id="mail-subject" value={subject} onChange={(e) => setSubject(e.target.value)} /></div>
            <div className="grid gap-1.5"><Label htmlFor="mail-body">Message</Label><Textarea id="mail-body" rows={12} value={body} onChange={(e) => setBody(e.target.value)} className="leading-relaxed" /></div>
            <Note>The recipient comes from the candidate record, not from the agent.</Note>
          </div>
        ),
      }
    case 'interview_schedule': {
      const slots = (payload.slots ?? []) as { id: string; start: string; end: string }[]
      return {
        canApprove: Boolean(slot), edits: () => ({ slot_id: slot }),
        after: "The panel's calendars are blocked and the invite goes to the candidate.",
        view: (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">Times when the whole panel is free. Pick one to confirm.</p>
            <div role="radiogroup" aria-label="Interview time" className="grid grid-cols-1 gap-2.5 sm:grid-cols-2">
              {slots.map((s) => {
                const d = new Date(s.start)
                const on = slot === s.id
                return (
                  <button key={s.id} type="button" role="radio" aria-checked={on} onClick={() => setSlot(s.id)}
                    className={cn('flex items-center gap-3 rounded-xl border p-3 text-left transition hover:border-primary/40', on && 'bg-brand-soft border-primary/50 ring-1 ring-violet/40')}>
                    <span className="grid w-12 shrink-0 overflow-hidden rounded-lg text-center ring-1 ring-border">
                      <span className="bg-brand py-px text-xs font-bold text-white uppercase">{d.toLocaleDateString(undefined, { month: 'short' })}</span>
                      <span className="font-heading py-0.5 text-lg font-bold">{d.getDate()}</span>
                    </span>
                    <span className="flex-1 text-sm"><span className="block font-semibold">{d.toLocaleDateString(undefined, { weekday: 'long' })}</span>
                      <span className="block text-muted-foreground">{d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })} – {new Date(s.end).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}</span></span>
                    {on && <CheckCircle2 className="size-5 text-violet" />}
                  </button>
                )
              })}
            </div>
          </div>
        ),
      }
    }
    case 'offer': {
      const band = (payload.band ?? {}) as { min?: string; max?: string; level?: string }
      const base = Number(payload.base_salary)
      const pos = Math.min(100, Math.max(0, ((base - Number(band.min)) / Math.max(1, Number(band.max) - Number(band.min))) * 100))
      const currency = String(payload.currency ?? 'INR')
      return {
        canApprove: true, edits: () => ({}),
        after: request.step < request.chain_length ? 'It moves to the next approver in the chain.' : 'The offer is approved and a recruiter can send it.',
        view: (
          <div className="space-y-5">
            <div>
              <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Base salary</p>
              <p className="mt-1 text-3xl font-semibold tabular">{money(String(payload.base_salary), currency)}</p>
              <div className="mt-3 max-w-md">
                <div className="relative h-2.5 rounded-full bg-foreground/8">
                  <div className="bg-brand absolute inset-y-0 left-0 rounded-full opacity-80" style={{ width: `${pos}%` }} />
                  <span className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-white" style={{ left: `${pos}%` }} />
                </div>
                <div className="mt-1.5 flex justify-between text-xs text-muted-foreground tabular"><span>{money(band.min, currency)}</span><span>Band {band.level}</span><span>{money(band.max, currency)}</span></div>
              </div>
            </div>
            <KeyValue items={[['Bonus', payload.bonus_percent ? `${String(payload.bonus_percent)}%` : '—'], ['Start date', String(payload.start_date ?? 'TBC')]]} />
            {Boolean(payload.rationale) && <p className="rounded-xl border bg-muted/50 p-3.5 text-sm leading-relaxed">{String(payload.rationale)}</p>}
            <Note>Step {request.step} of {request.chain_length}. HR approves first, then finance; each step needs a different person, and never the requester.</Note>
          </div>
        ),
      }
    }
    case 'shortlist_review': {
      const assessed = (payload.assessments ?? []) as { application_id: string; summary: { documented?: number; mandatory_gaps?: string[] } }[]
      const name = (id: string, index: number) => blind ? `Candidate ${index + 1}` : applications.data?.find((a) => a.id === id)?.candidate_name ?? id.slice(0, 8)
      const complete = assessed.every((a) => choices[a.application_id]?.decision && choices[a.application_id]?.reason.trim())
      const set = (id: string, patch: Partial<{ decision: string; reason: string }>) =>
        setChoices({ ...choices, [id]: { decision: choices[id]?.decision ?? '', reason: choices[id]?.reason ?? '', ...patch } })
      return {
        canApprove: assessed.length > 0 && complete,
        edits: () => ({ decisions: assessed.map((a) => ({
          application_id: a.application_id, decision: choices[a.application_id].decision, reason: choices[a.application_id].reason,
          ...(choices[a.application_id].decision === 'advance' ? { to_stage: 'shortlisted' } : {}),
        })) }),
        after: 'Each candidate moves to the stage you chose, with your reason in the audit trail.',
        view: (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">Decide each candidate with a reason. Open the <Link className="font-medium text-violet hover:underline" to={`/requisitions/${String(payload.requisition_id)}/review`}>screening view</Link> to see the evidence.</p>
            <div className="overflow-hidden rounded-xl border">
              <Table>
                <TableHeader className="bg-muted/50"><TableRow className="hover:bg-transparent">
                  {['Candidate', 'Evidence', 'Decision', 'Reason'].map((h) => <TableHead key={h} className="text-xs tracking-wider text-muted-foreground uppercase">{h}</TableHead>)}
                </TableRow></TableHeader>
                <TableBody>
                  {assessed.map((a, index) => (
                    <TableRow key={a.application_id}>
                      <TableCell><span className="flex items-center gap-2.5"><PersonAvatar name={blind ? a.application_id : name(a.application_id, index)} size={30} /><span className="font-semibold">{name(a.application_id, index)}</span></span></TableCell>
                      <TableCell className="text-[13px] whitespace-normal">
                        <span className="font-medium text-success">{a.summary.documented ?? 0} documented</span>
                        {a.summary.mandatory_gaps?.length ? <span className="block text-warning">Gaps: {a.summary.mandatory_gaps.join(', ')}</span> : null}
                      </TableCell>
                      <TableCell>
                        <Select value={choices[a.application_id]?.decision || undefined} onValueChange={(v) => set(a.application_id, { decision: v })}>
                          <SelectTrigger size="sm" className="w-32" aria-label={`Decision for ${name(a.application_id, index)}`}><SelectValue placeholder="Choose" /></SelectTrigger>
                          <SelectContent><SelectItem value="advance">Shortlist</SelectItem><SelectItem value="hold">Hold</SelectItem><SelectItem value="reject">Reject</SelectItem></SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell className="min-w-56"><Input className="h-8" value={choices[a.application_id]?.reason ?? ''} placeholder="Why?" aria-label={`Reason for ${name(a.application_id, index)}`}
                        onChange={(e) => set(a.application_id, { reason: e.target.value })} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        ),
      }
    }
    default:
      return {
        canApprove: true, edits: () => ({}), after: 'The request is marked approved.',
        view: <KeyValue items={Object.entries(payload).map(([k, v]) => [k.replaceAll('_', ' '), typeof v === 'object' ? JSON.stringify(v) : String(v)])} />,
      }
  }
}

function Decide({ request }: { request: ApprovalRequest }) {
  const decide = useApiV1ApprovalsDecideCreate()
  const editor = useEditor(request)
  const [asking, setAsking] = useState<ApprovalDecisionEnum | null>(null)
  const send = (decision: ApprovalDecisionEnum, reason = '') =>
    decide.mutate({ id: request.id, data: { decision, reason, edits: decision === 'approve' ? editor.edits() : {} } },
      { onSuccess: () => toast.success(decision === 'approve' ? 'Approved' : decision === 'reject' ? 'Rejected' : 'Changes requested'), onSettled: () => setAsking(null) })
  const open = request.status === 'pending' && request.can_decide
  return (
    <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1.65fr)_minmax(0,1fr)]">
      <Panel title="The draft" icon={KIND_ICON[request.kind] ?? <ClipboardCheck />} description={request.agent_run_id ? 'Drafted by an agent. Read it as a proposal: you can edit before approving.' : undefined}>
        {editor.view}
        <ErrorAlert error={decide.error} />
        {open && (
          <div className="mt-6 flex flex-wrap items-center gap-2 border-t pt-4">
            <Button size="lg" disabled={!editor.canApprove || decide.isPending} onClick={() => send('approve')}><CheckCircle2 /> Approve</Button>
            {['job_description', 'email', 'offer'].includes(request.kind) && <Button size="lg" variant="outline" onClick={() => setAsking('request_changes')}><RotateCcw /> Request changes</Button>}
            <Button size="lg" variant="destructive" onClick={() => setAsking('reject')}><XCircle /> Reject</Button>
            {!editor.canApprove && <span className="text-xs text-muted-foreground">Complete the form to approve.</span>}
          </div>
        )}
        {request.status === 'pending' && !request.can_decide && (
          <div className="mt-5"><Note tone="warning">Waiting for {request.required_roles.join(' or ').replaceAll('_', ' ')}. You can read it but not decide.</Note></div>
        )}
      </Panel>
      <div className="space-y-6">
        {open && (
          <Panel title="When you approve" icon={<MessageSquareWarning />}>
            <p className="text-sm leading-relaxed text-muted-foreground">{editor.after} Rejecting or asking for changes needs a reason, recorded with your name.</p>
          </Panel>
        )}
        <Panel title="History" icon={<History />}>
          <Timeline items={[
            { id: 'opened', title: 'Opened', time: shortDate(request.created_at), tone: 'info', icon: request.agent_run_id ? <Bot /> : <UserRound />,
              detail: `Needs ${request.required_roles.join(' or ').replaceAll('_', ' ')}` },
            ...request.decisions.map((d) => ({
              id: d.id, title: <span className="capitalize">{d.decision.replaceAll('_', ' ')}</span>, time: shortDate(d.created_at), detail: d.reason || undefined,
              tone: d.decision === 'approve' ? 'success' as const : d.decision === 'reject' ? 'destructive' as const : 'warning' as const,
            })),
          ]} />
        </Panel>
      </div>
      <ReasonDialog open={Boolean(asking)} title={asking === 'reject' ? 'Reject this draft' : 'Request changes'} destructive={asking === 'reject'}
        confirmLabel={asking === 'reject' ? 'Reject' : 'Request changes'} onClose={() => setAsking(null)} onConfirm={(reason) => asking && send(asking, reason)} />
    </div>
  )
}

export function ApprovalDetailPage() {
  const { id = '' } = useParams()
  const approval = useApiV1ApprovalsRetrieve(id)
  if (approval.isLoading) return <PageSkeleton />
  if (!approval.data) return <ErrorState error={approval.error} />
  const request = approval.data
  return (
    <>
      <DetailHero crumbs={[{ label: 'Approvals', to: '/approvals' }, { label: KIND_LABEL[request.kind] ?? request.kind }]}
        avatar={<span className={cn('grid size-14 place-items-center rounded-xl [&_svg]:size-7', KIND_TINT[request.kind] ?? 'bg-primary/15 text-violet')}>{KIND_ICON[request.kind] ?? <ClipboardCheck />}</span>}
        eyebrow={`${KIND_LABEL[request.kind] ?? request.kind} · step ${request.step} of ${request.chain_length}`} title={request.title}
        badges={<StatusBadge value={request.status} />} subtitle={request.summary}
        actions={request.agent_run_id && <Button variant="outline" asChild><Link to={`/agents/${request.agent_run_id}`}><Bot /> Agent run</Link></Button>}
        meta={[
          { icon: <CalendarDays />, label: 'Opened', value: shortDate(request.created_at) },
          { icon: <Users />, label: 'Needs', value: <span className="inline-block first-letter:uppercase">{request.required_roles.join(' or ').replaceAll('_', ' ').replace('hr admin', 'HR admin')}</span> },
          { icon: request.agent_run_id ? <Bot /> : <UserRound />, label: 'Drafted by', value: request.agent_run_id ? 'AI agent' : 'A colleague' },
          { icon: <RotateCcw />, label: 'Review round', value: request.review_round },
        ]}>
        {request.kind === 'offer' && (
          <Stages steps={['Drafted', 'HR approval', 'Finance approval', 'Approved']}
            active={request.status === 'approved' && request.step === request.chain_length ? 4 : request.step} failed={request.status === 'rejected'} />
        )}
      </DetailHero>
      <Decide key={`${request.id}-${request.status}-${request.step}`} request={request} />
    </>
  )
}
