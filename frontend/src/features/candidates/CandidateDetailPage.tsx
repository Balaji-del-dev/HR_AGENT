import { type ReactNode, useState } from 'react'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'
import { Award, Briefcase, CheckCheck, ClipboardCheck, EyeOff, FileText, GraduationCap, Mail, Phone, ShieldAlert, Sparkles, Wallet } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { ReasonDialog } from '@/components/app/dialogs'
import { DetailHero } from '@/components/app/detail'
import { Panel, Tag } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import { RunProgress } from '@/components/app/run-progress'
import { EmptyState, ErrorAlert, ErrorState, PageSkeleton } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { Timeline } from '@/components/app/timeline'
import { useSession } from '@/app/session'
import {
  useApiV1ApplicationsCommsRunsCreate, useApiV1ApplicationsFeedbackRunsCreate, useApiV1ApplicationsList,
  useApiV1ApplicationsOfferRunsCreate, useApiV1ApplicationsRetrieve,
} from '@/shared/api/generated/applications/applications'
import {
  useApiV1CandidatesConsentsCreate, useApiV1CandidatesFactsPartialUpdate, useApiV1CandidatesRetrieve,
} from '@/shared/api/generated/candidates/candidates'
import { useApiV1DeletionRequestsCreate } from '@/shared/api/generated/governance/governance'
import type { Application, CommsRunInKindEnum } from '@/shared/api/generated/model'
import { useMe } from '@/shared/hooks/useMe'
import { shortDate } from '@/shared/ui/common'
import { ResumeViewer } from '../review/ResumeViewer'
import { UploadResume } from './UploadResume'

type Evidence = { span_id: string; quote: string }
type Fact = { id: string; evidence: Evidence[]; confidence: number; needs_review: boolean; [k: string]: unknown }

function FactRow({ type, fact, title, meta, onFocus }: { type: 'skill' | 'experience' | 'education' | 'certification'; fact: Fact; title: string; meta?: string; onFocus: (id: string) => void }) {
  const confirm = useApiV1CandidatesFactsPartialUpdate()
  return (
    <li className="flex items-start gap-3 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">{title}{meta && <span className="font-normal text-muted-foreground"> · {meta}</span>}</p>
        <div className="mt-1 flex flex-wrap gap-1.5">
          {fact.evidence.map((e) => (
            <button key={e.span_id} type="button" onClick={() => onFocus(e.span_id)} title="Show in resume"
              className="max-w-full truncate rounded-md bg-primary/12 px-1.5 py-0.5 text-left text-xs text-foreground/85 ring-1 ring-primary/25 ring-inset transition hover:bg-primary/22">“{e.quote.slice(0, 70)}”</button>
          ))}
        </div>
      </div>
      {fact.needs_review ? (
        <Button size="sm" variant="outline" onClick={() => confirm.mutate({ factType: type, factId: fact.id, data: { changes: {} } }, { onSuccess: () => toast.success('Fact confirmed') })}>
          <CheckCheck /> Confirm {Math.round(fact.confidence * 100)}%
        </Button>
      ) : null}
    </li>
  )
}

function ApplicationCard({ application }: { application: Application }) {
  const { hasRole } = useMe()
  const detail = useApiV1ApplicationsRetrieve(application.id)
  const comms = useApiV1ApplicationsCommsRunsCreate()
  const feedback = useApiV1ApplicationsFeedbackRunsCreate()
  const offer = useApiV1ApplicationsOfferRunsCreate()
  const [kind, setKind] = useState<CommsRunInKindEnum>('update')
  const runId = comms.data?.id ?? feedback.data?.id ?? offer.data?.id
  const history = detail.data?.stage_history ?? []
  return (
    <div className="glass rounded-xl p-4">
      <div className="flex items-center gap-2">
        <Briefcase className="size-4 text-muted-foreground" />
        <Link to={`/requisitions/${application.requisition_id}/review`} className="flex-1 font-semibold hover:text-violet">{application.requisition_title}</Link>
        <StatusBadge value={application.stage} />
      </div>
      {history.length > 0 && (
        <div className="mt-4"><Timeline dense items={history.map((h) => ({ id: h.id, title: `${h.from_stage} → ${h.to_stage}`, detail: h.reason, time: shortDate(h.created_at), tone: h.to_stage === 'rejected' ? 'destructive' : 'primary' }))} /></div>
      )}
      {hasRole('hr_admin', 'recruiter') && (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t pt-3">
          <Select value={kind} onValueChange={(v) => setKind(v as CommsRunInKindEnum)}>
            <SelectTrigger size="sm" className="w-40" aria-label="Email type"><SelectValue /></SelectTrigger>
            <SelectContent><SelectItem value="update">Status update</SelectItem><SelectItem value="outreach">Outreach</SelectItem><SelectItem value="decline">Kind decline</SelectItem></SelectContent>
          </Select>
          <Button size="sm" variant="outline" onClick={() => comms.mutate({ id: application.id, data: { kind } })}><Mail /> Draft email</Button>
          <Button size="sm" variant="outline" onClick={() => feedback.mutate({ id: application.id })}><Sparkles /> Summarise feedback</Button>
          <Button size="sm" variant="outline" onClick={() => offer.mutate({ id: application.id })}><Wallet /> Draft offer</Button>
        </div>
      )}
      <ErrorAlert error={comms.error ?? feedback.error ?? offer.error} />
      {runId && <div className="mt-3"><RunProgress runId={runId} title="Agent working on this" /></div>}
    </div>
  )
}

export function CandidateDetailPage() {
  const { id = '' } = useParams()
  const { hasRole } = useMe()
  const blind = useSession((s) => s.blindReview)
  const candidate = useApiV1CandidatesRetrieve(id)
  const applications = useApiV1ApplicationsList({ candidate: id })
  const consent = useApiV1CandidatesConsentsCreate()
  const deletion = useApiV1DeletionRequestsCreate()
  const [focus, setFocus] = useState<string | null>(null)
  const [erase, setErase] = useState(false)
  if (candidate.isLoading) return <PageSkeleton />
  if (!candidate.data) return <ErrorState error={candidate.error} />
  const c = candidate.data
  const recruiter = hasRole('hr_admin', 'recruiter')
  const doc = c.documents.find((d) => d.status === 'processed')
  const facts = (x: unknown) => x as Fact[]
  const name = blind ? `Candidate ${c.id.slice(0, 4).toUpperCase()}` : c.full_name
  const groups: [string, ReactNode, ReactNode[]][] = [
    ['Skills', <Sparkles key="i" />, facts(c.skills).map((f) => <FactRow key={f.id} type="skill" fact={f} title={String(f.name)} onFocus={setFocus} />)],
    ['Experience', <Briefcase key="i" />, facts(c.experience).map((f) => <FactRow key={f.id} type="experience" fact={f} title={String(f.title)}
      meta={`${f.organization ? `${String(f.organization)}, ` : ''}${String(f.start || '?')}–${String(f.end || 'now')}`} onFocus={setFocus} />)],
    ['Education', <GraduationCap key="i" />, facts(c.education).map((f) => <FactRow key={f.id} type="education" fact={f} title={String(f.degree)} meta={String(f.year || '')} onFocus={setFocus} />)],
    ['Certifications', <Award key="i" />, facts(c.certifications).map((f) => <FactRow key={f.id} type="certification" fact={f} title={String(f.name)} onFocus={setFocus} />)],
  ]

  return (
    <>
      <DetailHero crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Candidates', to: '/candidates' }, { label: name }]}
        avatar={<PersonAvatar name={blind ? c.id : c.full_name} size={72} />} eyebrow={`Candidate · ${(c.source ?? 'applied').replaceAll('_', ' ')}`} title={name}
        badges={<>
          {(applications.data?.results ?? []).map((a) => <StatusBadge key={a.id} value={a.stage} />)}
          {c.in_talent_pool && <Tag tone="success">Talent pool</Tag>}
          {blind && <Tag tone="violet"><EyeOff className="size-3" /> Blind review</Tag>}
        </>}
        subtitle={c.is_anonymized ? 'Personal data erased on request.' : blind ? 'Identity hidden while you review evidence.' : (
          <span className="flex flex-wrap gap-x-4 gap-y-1">{c.email && <span className="flex items-center gap-1.5"><Mail className="size-4" />{c.email}</span>}{c.phone && <span className="flex items-center gap-1.5"><Phone className="size-4" />{c.phone}</span>}</span>
        )}
        actions={<>
          {(applications.data?.results ?? [])[0] && <Button variant="outline" asChild><Link to={`/requisitions/${applications.data?.results?.[0]?.requisition_id}/review`}><ClipboardCheck /> Screening</Link></Button>}
          {recruiter && !c.is_anonymized && <Button variant="destructive" onClick={() => setErase(true)}><ShieldAlert /> Erasure request</Button>}
        </>}
        meta={[
          { icon: <Briefcase />, label: 'Applications', value: applications.data?.count ?? 0 },
          { icon: <Sparkles />, label: 'Skills found', value: facts(c.skills).length },
          { icon: <GraduationCap />, label: 'Roles · degrees', value: `${facts(c.experience).length} · ${facts(c.education).length}` },
          { icon: <FileText />, label: 'Resume', value: doc ? `${doc.page_count} page${doc.page_count === 1 ? '' : 's'}${doc.ocr_used ? ' · OCR' : ''}` : 'Not processed' },
        ]} />
      <ErrorAlert error={consent.error ?? deletion.error} />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        <Tabs defaultValue="profile">
          <TabsList><TabsTrigger value="profile">Profile</TabsTrigger><TabsTrigger value="applications">Applications ({applications.data?.count ?? 0})</TabsTrigger><TabsTrigger value="privacy">Consent</TabsTrigger></TabsList>
          <TabsContent value="profile" className="mt-4">
            <Panel title="Extracted profile" description="Every fact links to the resume line it came from. Click a quote to see it.">
              {c.profile?.missing_sections?.length ? <p className="mb-2 rounded-xl bg-warning/10 px-3 py-2 text-[13px]">Not in the resume: {c.profile.missing_sections.join(', ')}</p> : null}
              {groups.map(([label, icon, rows]) => (
                <div key={label} className="border-t py-2 first:border-t-0">
                  <p className="flex items-center gap-2 pt-1 text-[13px] font-semibold text-muted-foreground [&_svg]:size-4">{icon}{label}</p>
                  {rows.length ? <ul className="divide-y">{rows}</ul> : <p className="py-2 text-sm text-muted-foreground">None found.</p>}
                </div>
              ))}
            </Panel>
          </TabsContent>
          <TabsContent value="applications" className="mt-4 space-y-3">
            {(applications.data?.results ?? []).length === 0 ? <Panel><EmptyState>Not applied to any job yet.</EmptyState></Panel>
              : applications.data?.results?.map((a) => <ApplicationCard key={a.id} application={a} />)}
          </TabsContent>
          <TabsContent value="privacy" className="mt-4">
            <Panel title="Consent" description="Withdrawing consent stops all processing for that purpose at once.">
              {(['application', 'talent_pool'] as const).map((purpose) => {
                const current = c.consents.find((x) => x.purpose === purpose)
                return (
                  <label key={purpose} className="flex items-center gap-3 border-t py-3 first:border-t-0">
                    <span className="flex-1"><span className="block text-sm font-medium">{purpose === 'application' ? 'This application' : 'Talent pool'}</span>
                      <span className="block text-xs text-muted-foreground">{current ? `${current.source || 'Recorded'} · ${shortDate(current.granted_at)}` : 'Not given'}</span></span>
                    <Switch checked={Boolean(current?.is_active)} disabled={!recruiter || c.is_anonymized}
                      onCheckedChange={(v) => consent.mutate({ id, data: { purpose, granted: v, source: 'updated by recruiter' } })} />
                  </label>
                )
              })}
            </Panel>
          </TabsContent>
        </Tabs>
        <div className="space-y-4">
          <Panel title="Resume" description={doc ? `${doc.original_name} · ${doc.page_count} page${doc.page_count === 1 ? '' : 's'}${doc.ocr_used ? ' · OCR' : ''}` : 'No processed resume yet'}
            action={doc && <StatusBadge value={doc.status} />}>
            {doc?.injection_suspected && <p className="mb-3 rounded-xl bg-warning/10 px-3 py-2 text-[13px]">This resume contains text that reads like instructions to an AI. It is shown, marked, and never followed.</p>}
            {recruiter && !c.is_anonymized && <UploadResume candidateId={id} />}
            {c.documents.filter((d) => d.status !== 'processed').map((d) => (
              <p key={d.id} className="mt-2 flex items-center gap-2 text-[13px]"><FileText className="size-4" />{d.original_name}<StatusBadge value={d.status} />{d.error}</p>
            ))}
          </Panel>
          {doc && <ResumeViewer documentId={doc.id} highlighted={new Set(focus ? [focus] : [])} focus={focus} blind={blind} />}
        </div>
      </div>
      <ReasonDialog open={erase} title="Log an erasure request" description="The candidate asked us to erase their data. An HR admin completes the request from Settings." confirmLabel="Log request" destructive required={false}
        onClose={() => setErase(false)} onConfirm={(reason) => deletion.mutate({ data: { candidate_id: id, reason } }, { onSuccess: () => { setErase(false); toast.success('Erasure request logged') } })} />
    </>
  )
}
