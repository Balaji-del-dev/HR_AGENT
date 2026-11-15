import { useState, type ReactNode } from 'react'
import { toast } from 'sonner'
import {
  Bot, Check, Cog, FileClock, Gavel, KeyRound, Mail, Minus, Plus, ScrollText, ShieldCheck, Trash2, UserRound, Users, Wallet,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Skeleton } from '@/components/ui/skeleton'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { DataTable } from '@/components/app/data-table'
import { PageHeader, Panel, Tag } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import { EmptyState, ErrorAlert } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { useApiV1MembersList } from '@/shared/api/generated/auth/auth'
import { useApiV1EmailTemplatesCreate, useApiV1EmailTemplatesList } from '@/shared/api/generated/communications/communications'
import {
  useApiV1AuditEventsList, useApiV1DeletionRequestsCompleteCreate, useApiV1DeletionRequestsList, useApiV1IncidentsList,
  useApiV1RetentionPoliciesCreate, useApiV1RetentionPoliciesList,
} from '@/shared/api/generated/governance/governance'
import { useApiV1JdTemplatesList } from '@/shared/api/generated/jobs/jobs'
import type { AuditEvent, CompBand, DeletionRequest, EmailKindEnum, MemberOut, TargetEnum } from '@/shared/api/generated/model'
import { useApiV1PoliciesMatrixRetrieve } from '@/shared/api/generated/policies/policies'
import { useApiV1CompBandsCreate, useApiV1CompBandsList } from '@/shared/api/generated/requisitions/requisitions'
import { useMe } from '@/shared/hooks/useMe'
import { money, shortDate } from '@/shared/ui/common'

const ROLE_LABEL: Record<string, string> = {
  hr_admin: 'HR admin', recruiter: 'Recruiter', hiring_manager: 'Hiring manager', interviewer: 'Interviewer', finance_approver: 'Finance approver', auditor: 'Auditor',
}

function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return <div className={cn('grid gap-1.5', className)}><Label className="text-[13px]">{label}</Label>{children}</div>
}

function CompBands() {
  const bands = useApiV1CompBandsList()
  const create = useApiV1CompBandsCreate()
  const [form, setForm] = useState({ department: 'Engineering', level: '', min_salary: '', max_salary: '', currency: 'INR' })
  return (
    <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
      <Panel flush className="overflow-hidden" title="Pay bands" icon={<Wallet />} description="Offers are drafted inside these ranges and cannot leave them.">
        <DataTable rows={bands.data?.results} rowKey={(b) => b.id} loading={bands.isLoading} exportName="pay-bands"
          facets={[{ key: 'dept', label: 'Department', value: (b) => b.department, format: (v) => v }]}
          empty={<EmptyState icon={<Wallet />} title="No pay bands">Add one to let the offer agent draft inside it.</EmptyState>}
          columns={[
            { key: 'department', header: 'Department', sort: (b: CompBand) => b.department, cell: (b: CompBand) => <span className="font-semibold">{b.department}</span> },
            { key: 'level', header: 'Level', sort: (b: CompBand) => b.level, cell: (b: CompBand) => <Tag tone="violet">{b.level}</Tag> },
            { key: 'min', header: 'Minimum', align: 'right', sort: (b: CompBand) => Number(b.min_salary), cell: (b: CompBand) => <span className="tabular">{money(b.min_salary, b.currency)}</span> },
            { key: 'max', header: 'Maximum', align: 'right', sort: (b: CompBand) => Number(b.max_salary), cell: (b: CompBand) => <span className="tabular">{money(b.max_salary, b.currency)}</span> },
          ]} />
      </Panel>
      <Panel title="Add a band" icon={<Plus />}>
        <ErrorAlert error={create.error} />
        <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
          <Field label="Department"><Input value={form.department} onChange={(e) => setForm({ ...form, department: e.target.value })} /></Field>
          <Field label="Level"><Input value={form.level} placeholder="L4" onChange={(e) => setForm({ ...form, level: e.target.value })} /></Field>
          <Field label="Minimum"><Input inputMode="numeric" value={form.min_salary} onChange={(e) => setForm({ ...form, min_salary: e.target.value })} /></Field>
          <Field label="Maximum"><Input inputMode="numeric" value={form.max_salary} onChange={(e) => setForm({ ...form, max_salary: e.target.value })} /></Field>
          <Field label="Currency"><Input value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })} /></Field>
        </div>
        <Button className="mt-4" disabled={create.isPending} onClick={() => create.mutate({ data: form }, { onSuccess: () => toast.success('Pay band added') })}><Plus /> Add band</Button>
      </Panel>
    </div>
  )
}

function Templates() {
  const jd = useApiV1JdTemplatesList()
  const email = useApiV1EmailTemplatesList()
  const create = useApiV1EmailTemplatesCreate()
  const [form, setForm] = useState({ key: '', name: '', kind: 'update' as EmailKindEnum, subject: '', body: '' })
  return (
    <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-2">
      <div className="space-y-6">
        <Panel title="JD templates" icon={<ScrollText />} description="The JD agent writes from these.">
          <ul className="divide-y divide-border/70">
            {(jd.data?.results ?? []).map((t) => <li key={t.id} className="flex items-center gap-3 py-2.5"><ScrollText className="size-4 text-violet" /><span className="flex-1 font-medium">{t.name}</span><Tag>{t.department || 'Any department'}</Tag></li>)}
          </ul>
        </Panel>
        <Panel title="Email templates" icon={<Mail />} description="Agents fill the placeholders; a person approves every send.">
          <ul className="divide-y divide-border/70">
            {(email.data?.results ?? []).map((t) => (
              <li key={t.id} className="py-2.5">
                <p className="flex items-center gap-2"><span className="flex-1 font-medium">{t.name}</span><Tag tone="cyan" className="capitalize">{t.kind}</Tag></p>
                <p className="mt-0.5 truncate text-[13px] text-muted-foreground">{t.subject}</p>
              </li>
            ))}
          </ul>
        </Panel>
      </div>
      <Panel title="New email template" icon={<Plus />}>
        <ErrorAlert error={create.error} />
        <div className="grid gap-3.5">
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-3">
            <Field label="Key"><Input value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value })} placeholder="status_update_v2" /></Field>
            <Field label="Name"><Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
            <Field label="Kind">
              <Select value={form.kind} onValueChange={(v) => setForm({ ...form, kind: v as EmailKindEnum })}>
                <SelectTrigger className="w-full" aria-label="Kind"><SelectValue /></SelectTrigger>
                <SelectContent>{['outreach', 'update', 'decline', 'invite', 'offer'].map((k) => <SelectItem key={k} value={k} className="capitalize">{k}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
          </div>
          <Field label="Subject"><Input value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} /></Field>
          <Field label="Body"><Textarea rows={6} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} /></Field>
          <p className="text-xs text-muted-foreground">Placeholders: <code className="font-mono">{'{{ candidate_first_name }}'}</code>, <code className="font-mono">{'{{ job_title }}'}</code>, <code className="font-mono">{'{{ company_name }}'}</code>, <code className="font-mono">{'{{ recruiter_name }}'}</code></p>
          <Button className="w-fit" disabled={create.isPending} onClick={() => create.mutate({ data: form }, { onSuccess: () => toast.success('Template added') })}><Plus /> Add email template</Button>
        </div>
      </Panel>
    </div>
  )
}

function Retention() {
  const policies = useApiV1RetentionPoliciesList()
  const save = useApiV1RetentionPoliciesCreate()
  const deletions = useApiV1DeletionRequestsList()
  const complete = useApiV1DeletionRequestsCompleteCreate()
  const [target, setTarget] = useState<TargetEnum>('candidates')
  const [days, setDays] = useState('365')
  return (
    <div className="space-y-6">
      <ErrorAlert error={save.error ?? complete.error} />
      <div className="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Panel title="Retention" icon={<FileClock />} description="Data older than this is deleted by the nightly job.">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {(policies.data?.results ?? []).map((p) => (
              <div key={p.id} className="rounded-xl border bg-muted/40 p-4">
                <p className="text-xs text-muted-foreground capitalize">{p.target.replaceAll('_', ' ')}</p>
                <p className="font-heading mt-1 text-2xl font-bold tabular">{p.retain_days}<span className="ml-1 text-sm font-medium text-muted-foreground">days</span></p>
                <p className={cn('mt-1 text-xs font-medium', p.is_active ? 'text-success' : 'text-muted-foreground')}>{p.is_active ? 'Active' : 'Off'}</p>
              </div>
            ))}
          </div>
        </Panel>
        <Panel title="Change a retention period" icon={<Cog />}>
          <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2">
            <Field label="Applies to">
              <Select value={target} onValueChange={(v) => setTarget(v as TargetEnum)}>
                <SelectTrigger className="w-full" aria-label="Applies to"><SelectValue /></SelectTrigger>
                <SelectContent>{['candidates', 'documents', 'agent_runs'].map((t) => <SelectItem key={t} value={t} className="capitalize">{t.replaceAll('_', ' ')}</SelectItem>)}</SelectContent>
              </Select>
            </Field>
            <Field label="Keep for (days)"><Input type="number" value={days} onChange={(e) => setDays(e.target.value)} /></Field>
          </div>
          <Button className="mt-4" disabled={save.isPending} onClick={() => save.mutate({ data: { target, retain_days: Number(days) } }, { onSuccess: () => toast.success('Retention saved') })}>Save</Button>
        </Panel>
      </div>
      <Panel flush className="overflow-hidden" title="Erasure requests" icon={<Trash2 />} description="Completing a request erases the person's data and keeps an anonymous record that it happened.">
        <DataTable rows={deletions.data?.results} rowKey={(d) => d.id} loading={deletions.isLoading} facets={[{ key: 'status', label: 'Status', value: (d) => d.status }]}
          empty={<EmptyState icon={<ShieldCheck />} title="No erasure requests">Requests logged from a candidate's page appear here.</EmptyState>}
          columns={[
            { key: 'ref', header: 'Candidate reference', cell: (d: DeletionRequest) => <span className="font-mono text-xs">{d.candidate_ref.slice(0, 16)}</span> },
            { key: 'reason', header: 'Reason', hide: 'md', cell: (d: DeletionRequest) => <span className="text-muted-foreground">{d.reason || '—'}</span> },
            { key: 'status', header: 'Status', sort: (d: DeletionRequest) => d.status, cell: (d: DeletionRequest) => <StatusBadge value={d.status} /> },
            { key: 'logged', header: 'Logged', sort: (d: DeletionRequest) => d.created_at, cell: (d: DeletionRequest) => <span className="text-muted-foreground">{shortDate(d.created_at)}</span> },
            { key: 'action', header: '', hideable: false, align: 'right', cell: (d: DeletionRequest) => d.status === 'pending'
              ? <Button size="sm" variant="destructive" onClick={() => complete.mutate({ id: d.id }, { onSuccess: () => toast.success('Data erased') })}><Trash2 /> Erase data</Button> : null },
          ]} />
      </Panel>
    </div>
  )
}

const ACTOR_ICON: Record<string, ReactNode> = { user: <UserRound className="size-3.5" />, agent: <Bot className="size-3.5" />, system: <Cog className="size-3.5" /> }

function Audit() {
  const events = useApiV1AuditEventsList()
  const incidents = useApiV1IncidentsList()
  return (
    <div className="space-y-6">
      <Panel title="Incidents" icon={<ShieldCheck />}>
        {(incidents.data?.results ?? []).length === 0
          ? <p className="flex items-center gap-2 rounded-xl bg-success/10 px-3.5 py-2.5 text-sm text-success ring-1 ring-success/25 ring-inset"><ShieldCheck className="size-4" /> No security, privacy or AI incidents.</p>
          : (
            <ul className="divide-y divide-border/70">
              {incidents.data?.results?.map((i) => (
                <li key={i.id} className="flex items-center gap-3 py-2.5">
                  <span className="flex-1"><span className="block font-medium">{i.title}</span><span className="text-xs text-muted-foreground capitalize">{i.kind.replaceAll('_', ' ')} · {shortDate(i.created_at)}</span></span>
                  <Tag tone={i.severity === 'high' || i.severity === 'critical' ? 'danger' : 'warning'} className="capitalize">{i.severity}</Tag>
                  <StatusBadge value={i.status} />
                </li>
              ))}
            </ul>
          )}
      </Panel>
      <Panel flush className="overflow-hidden" title="Audit log" icon={<ScrollText />} description="Append-only. The database refuses edits and deletes, for everyone.">
        <DataTable rows={events.data?.results} rowKey={(e) => e.id} loading={events.isLoading} pageSize={20} exportName="audit-log"
          filterText={(e) => `${e.action} ${e.target_type} ${e.actor_id ?? ''} ${e.target_id}`} filterPlaceholder="Search action or target" initialSort={{ key: 'when', desc: true }}
          facets={[
            { key: 'actor', label: 'Actor', value: (e) => e.actor_type },
            { key: 'target', label: 'Target', value: (e) => e.target_type },
            { key: 'area', label: 'Area', value: (e) => e.action.split('.')[0] },
          ]}
          columns={[
            { key: 'action', header: 'Action', sort: (e: AuditEvent) => e.action, cell: (e: AuditEvent) => <span className="font-mono text-[13px] font-medium">{e.action}</span> },
            { key: 'actor', header: 'Actor', sort: (e: AuditEvent) => e.actor_type, cell: (e: AuditEvent) => (
              <span className={cn('inline-flex items-center gap-1.5 rounded-lg px-2 py-0.5 text-xs font-semibold capitalize ring-1 ring-inset',
                e.actor_type === 'agent' ? 'bg-primary/15 text-violet ring-primary/30' : e.actor_type === 'user' ? 'bg-info/12 text-info ring-info/25' : 'bg-muted text-muted-foreground ring-border')}>
                {ACTOR_ICON[e.actor_type]}{e.actor_type}{e.actor_id ? <span className="font-mono font-normal opacity-70">{e.actor_id.slice(0, 6)}</span> : null}
              </span>
            ) },
            { key: 'target', header: 'Target', hide: 'md', sort: (e: AuditEvent) => e.target_type, cell: (e: AuditEvent) => <span className="text-muted-foreground"><span className="capitalize">{e.target_type}</span> <span className="font-mono text-xs">{e.target_id?.slice(0, 8)}</span></span> },
            { key: 'run', header: 'Agent run', hide: 'lg', cell: (e: AuditEvent) => e.run_id ? <span className="font-mono text-xs text-violet">{e.run_id.slice(0, 8)}</span> : <span className="text-muted-foreground">—</span> },
            { key: 'when', header: 'When', sort: (e: AuditEvent) => e.created_at, cell: (e: AuditEvent) => <span className="tabular text-muted-foreground">{shortDate(e.created_at)}</span> },
          ]} />
      </Panel>
    </div>
  )
}

function Members() {
  const members = useApiV1MembersList()
  return (
    <Panel flush className="overflow-hidden" title="Members" icon={<Users />} description="Roles decide what each person sees and which agents and tools they can use.">
      <DataTable rows={members.data} rowKey={(m) => m.user_id} loading={members.isLoading} filterText={(m) => `${m.full_name} ${m.username}`} filterPlaceholder="Search people"
        facets={[{ key: 'role', label: 'Role', value: (m) => [...m.roles] }]} exportName="members"
        columns={[
          { key: 'name', header: 'Member', sort: (m: MemberOut) => m.full_name, cell: (m: MemberOut) => (
            <div className="flex items-center gap-3"><PersonAvatar name={m.full_name} size={34} /><span><span className="block font-semibold">{m.full_name}</span><span className="block text-xs text-muted-foreground">{m.username}</span></span></div>
          ) },
          { key: 'roles', header: 'Roles', csv: (m: MemberOut) => m.roles.join(' '), cell: (m: MemberOut) => <div className="flex flex-wrap gap-1">{m.roles.map((r) => <Tag key={r} tone="violet">{ROLE_LABEL[r] ?? r}</Tag>)}</div> },
        ]} />
    </Panel>
  )
}

/** Live policy table from the server: which roles may start each agent and use each tool. */
function PermissionMatrix() {
  const matrix = useApiV1PoliciesMatrixRetrieve()
  if (!matrix.data) return <Skeleton className="h-96 rounded-xl" />
  const { roles, runs, tools, rules } = matrix.data
  const grid = (title: string, icon: ReactNode, rows: Record<string, string[]>, mono?: boolean) => (
    <Panel title={title} icon={icon} flush className="overflow-hidden">
      <div className="overflow-x-auto">
        <Table aria-label={title}>
          <TableHeader className="bg-muted/50">
            <TableRow className="hover:bg-transparent">
              <TableHead className="pl-5" />
              {roles.map((r) => <TableHead key={r} className="text-center text-[13px] text-muted-foreground">{ROLE_LABEL[r] ?? r}</TableHead>)}
            </TableRow>
          </TableHeader>
          <TableBody>
            {Object.entries(rows).map(([name, allowed]) => (
              <TableRow key={name}>
                <TableCell className={cn('pl-5 font-medium', mono ? 'font-mono text-[13px]' : 'capitalize')}>{mono ? name : name.replaceAll('_', ' ')}</TableCell>
                {roles.map((r) => (
                  <TableCell key={r} className="text-center">
                    {allowed.includes(r)
                      ? <span className="inline-grid size-6 place-items-center rounded-full bg-success/15 text-success" aria-label="allowed"><Check className="size-3.5" /></span>
                      : <span className="inline-grid size-6 place-items-center text-muted-foreground/40" aria-label="not allowed"><Minus className="size-3.5" /></span>}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Panel>
  )
  return (
    <div className="space-y-6">
      <p className="glass flex items-center gap-2.5 rounded-xl px-4 py-3 text-sm"><KeyRound className="size-4 text-violet" /> This is the policy engine's own table, read from the server. Code enforces it on every call, whatever the model says.</p>
      {grid('Who can start each agent', <Bot />, runs)}
      {grid('Tools each role may have called for them', <Cog />, tools, true)}
      <Panel title="Business rules" icon={<Gavel />}>
        <ul className="grid grid-cols-1 gap-2.5 md:grid-cols-2">
          {(rules as { id: string; rule: string }[]).map((r) => (
            <li key={r.id} className="flex gap-3 rounded-xl border bg-muted/40 p-3 text-sm"><Gavel className="mt-0.5 size-4 shrink-0 text-violet" />{r.rule}</li>
          ))}
        </ul>
      </Panel>
    </div>
  )
}

export function AdminPage() {
  const { hasRole } = useMe()
  const tabs: [string, string, ReactNode][] = hasRole('hr_admin')
    ? [['bands', 'Pay bands', <Wallet key="i" />], ['templates', 'Templates', <ScrollText key="i" />], ['members', 'Members', <Users key="i" />],
      ['permissions', 'Permissions', <KeyRound key="i" />], ['retention', 'Retention and erasure', <FileClock key="i" />], ['audit', 'Audit and incidents', <ShieldCheck key="i" />]]
    : [['permissions', 'Permissions', <KeyRound key="i" />], ['audit', 'Audit and incidents', <ShieldCheck key="i" />]]
  return (
    <>
      <PageHeader title="Settings" crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Settings' }]}
        description="Configuration for HR admins. The audit log is append-only and read-only here." />
      <Tabs defaultValue={tabs[0][0]}>
        <TabsList className="mb-5 h-auto flex-wrap">
          {tabs.map(([value, label, icon]) => <TabsTrigger key={value} value={value} className="h-8">{icon}{label}</TabsTrigger>)}
        </TabsList>
        <TabsContent value="bands"><CompBands /></TabsContent>
        <TabsContent value="templates"><Templates /></TabsContent>
        <TabsContent value="members"><Members /></TabsContent>
        <TabsContent value="permissions"><PermissionMatrix /></TabsContent>
        <TabsContent value="retention"><Retention /></TabsContent>
        <TabsContent value="audit"><Audit /></TabsContent>
      </Tabs>
    </>
  )
}
