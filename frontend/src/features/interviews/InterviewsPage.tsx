import { useState } from 'react'
import { Link } from 'react-router'
import { toast } from 'sonner'
import { CalendarDays, ClipboardPen, Plus, Search } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { DataTable } from '@/components/app/data-table'
import { StatusCards } from '@/components/app/status-cards'
import { PageHeader, Panel } from '@/components/app/page'
import { PeopleStack, PersonAvatar } from '@/components/app/people'
import { RunProgress } from '@/components/app/run-progress'
import { EmptyState, ErrorAlert } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { useApiV1ApplicationsList } from '@/shared/api/generated/applications/applications'
import { useApiV1MembersList } from '@/shared/api/generated/auth/auth'
import { apiV1InterviewsList, useApiV1InterviewsCreate, useApiV1InterviewsScheduleRunsCreate } from '@/shared/api/generated/interviews/interviews'
import { useAllPages } from '@/shared/hooks/useAllPages'
import type { Interview } from '@/shared/api/generated/model'
import { useMe } from '@/shared/hooks/useMe'

function When({ value }: { value: string | null }) {
  if (!value) return <span className="text-sm text-muted-foreground">Not scheduled</span>
  const d = new Date(value)
  return (
    <span className="flex items-center gap-3">
      <span className="grid w-11 shrink-0 overflow-hidden rounded-lg text-center ring-1 ring-border">
        <span className="bg-brand py-px text-xs font-bold tracking-wider text-white uppercase">{d.toLocaleDateString(undefined, { month: 'short' })}</span>
        <span className="font-heading py-0.5 text-[17px] leading-tight font-bold">{d.getDate()}</span>
      </span>
      <span className="text-sm"><span className="block font-medium">{d.toLocaleDateString(undefined, { weekday: 'long' })}</span>
        <span className="block text-xs text-muted-foreground">{d.toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' })}</span></span>
    </span>
  )
}

function NewInterview({ open, onClose }: { open: boolean; onClose: () => void }) {
  const shortlisted = useApiV1ApplicationsList({ stage: 'shortlisted' })
  const inInterview = useApiV1ApplicationsList({ stage: 'interview' })
  const members = useApiV1MembersList()
  const create = useApiV1InterviewsCreate()
  const [applicationId, setApplicationId] = useState('')
  const [title, setTitle] = useState('Technical interview')
  const [panel, setPanel] = useState<string[]>([])
  const candidates = [...(shortlisted.data?.results ?? []), ...(inInterview.data?.results ?? [])]
  const interviewers = (members.data ?? []).filter((m) => m.roles.some((r) => ['interviewer', 'hiring_manager', 'recruiter'].includes(r)))
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="font-heading text-xl">New interview</DialogTitle>
          <DialogDescription>Pick the candidate and the panel. The scheduling agent then finds times everyone is free.</DialogDescription>
        </DialogHeader>
        <ErrorAlert error={create.error} />
        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label>Candidate</Label>
            <Select value={applicationId || undefined} onValueChange={setApplicationId}>
              <SelectTrigger className="w-full" aria-label="Candidate"><SelectValue placeholder="Shortlisted or in interview" /></SelectTrigger>
              <SelectContent>{candidates.map((a) => <SelectItem key={a.id} value={a.id}>{a.candidate_name} · {a.requisition_title}</SelectItem>)}</SelectContent>
            </Select>
          </div>
          <div className="grid gap-1.5"><Label htmlFor="ititle">Title</Label><Input id="ititle" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
          <div className="grid gap-1.5">
            <Label>Panel</Label>
            <ul className="max-h-56 space-y-1 overflow-y-auto rounded-xl border p-1.5">
              {interviewers.map((m) => (
                <li key={m.user_id}>
                  <label className={cn('flex cursor-pointer items-center gap-3 rounded-lg px-2 py-2 hover:bg-accent', panel.includes(m.user_id) && 'bg-primary/10')}>
                    <Checkbox checked={panel.includes(m.user_id)} onCheckedChange={(on) => setPanel(on ? [...panel, m.user_id] : panel.filter((p) => p !== m.user_id))} />
                    <PersonAvatar name={m.full_name} size={28} />
                    <span className="flex-1 text-sm font-medium">{m.full_name}</span>
                    <span className="text-xs text-muted-foreground capitalize">{m.roles.join(', ').replaceAll('_', ' ')}</span>
                  </label>
                </li>
              ))}
            </ul>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button disabled={!applicationId || panel.length === 0 || create.isPending}
            onClick={() => create.mutate({ data: { application_id: applicationId, title, panel_user_ids: panel } }, { onSuccess: () => { toast.success('Interview created'); onClose() } })}>Create interview</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function InterviewsPage() {
  const { hasRole } = useMe()
  const recruiter = hasRole('hr_admin', 'recruiter')
  const [mine, setMine] = useState(!recruiter)
  const [open, setOpen] = useState(false)
  const interviews = useAllPages(['interviews', mine], (page) => apiV1InterviewsList({ ...(mine ? { mine: true } : {}), page }))
  const schedule = useApiV1InterviewsScheduleRunsCreate()
  const members = useApiV1MembersList()
  const names = new Map((members.data ?? []).map((m) => [m.user_id, m.full_name]))
  const [view, setView] = useState('all')
  const all = interviews.data?.results ?? []
  const shown = view === 'all' ? all : all.filter((i) => i.status === view)
  return (
    <>
      <PageHeader title="Interviews" crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Interviews' }]}
        description="The scheduling agent proposes times from the panel's calendars. A recruiter confirms one."
        actions={<>
          <label className="glass flex h-9 items-center gap-2.5 rounded-xl px-3 text-sm">Only mine <Switch checked={mine} onCheckedChange={setMine} aria-label="Only mine" /></label>
          {recruiter && <Button onClick={() => setOpen(true)}><Plus /> New interview</Button>}
        </>} />
      <StatusCards items={[['all', 'All'], ['proposed', 'Waiting for a time'], ['scheduled', 'Scheduled'], ['completed', 'Completed'], ['cancelled', 'Cancelled']].map(([value, label]) => ({ value, label, count: value === 'all' ? all.length : all.filter((i) => i.status === value).length }))} value={view} onChange={setView} />
      <ErrorAlert error={interviews.error ?? schedule.error} />
      {schedule.data && <div className="mb-6"><RunProgress runId={schedule.data.id} title="Interview scheduling agent" /></div>}
      <Panel flush className="overflow-hidden">
        <DataTable rows={shown} rowKey={(i) => i.id} noun="interviews" loading={interviews.isLoading} exportName="interviews"
          filterText={(i) => `${i.candidate_name} ${i.requisition_title} ${i.title}`} filterPlaceholder="Search candidate, job or title"
          initialSort={{ key: 'when', desc: false }}
          facets={[
            { key: 'job', label: 'Job', value: (i) => i.requisition_title, format: (v) => v },
            { key: 'round', label: 'Round', value: (i) => String(i.round), format: (v) => `Round ${v}` },
          ]}
          empty={<EmptyState title="No interviews" icon={<CalendarDays />}>{mine ? 'No interviews are assigned to you.' : 'Create one for a shortlisted candidate.'}</EmptyState>}
          columns={[
            { key: 'candidate', header: 'Candidate', sort: (i: Interview) => i.candidate_name, cell: (i: Interview) => (
              <div className="flex items-center gap-3"><PersonAvatar name={i.candidate_name} size={36} />
                <div className="min-w-0"><p className="truncate font-semibold">{i.candidate_name}</p><p className="truncate text-xs text-muted-foreground">{i.requisition_title}</p></div></div>
            ) },
            { key: 'title', header: 'Interview', hide: 'md', sort: (i: Interview) => i.title, cell: (i: Interview) => (
              <span><span className="block font-medium">{i.title}</span><span className="block text-xs text-muted-foreground">Round {i.round} · {i.duration_minutes} min</span></span>
            ) },
            { key: 'when', header: 'When', sort: (i: Interview) => i.scheduled_start ?? '9999', csv: (i: Interview) => i.scheduled_start ?? '', cell: (i: Interview) => <When value={i.scheduled_start} /> },
            { key: 'panel', header: 'Panel', hide: 'sm', cell: (i: Interview) => <PeopleStack names={[...i.panel_user_ids].map((id) => names.get(id) ?? 'Panelist')} /> },
            { key: 'status', header: 'Status', sort: (i: Interview) => i.status, cell: (i: Interview) => <StatusBadge value={i.status} /> },
            { key: 'action', header: '', hideable: false, align: 'right', cell: (i: Interview) => i.status === 'proposed' && recruiter
              ? <Button size="sm" variant="outline" disabled={schedule.isPending} onClick={() => schedule.mutate({ id: i.id })}><Search /> Find times</Button>
              : i.status !== 'proposed' ? <Button size="sm" variant="outline" asChild><Link to={`/interviews/${i.id}/scorecard`}><ClipboardPen /> Scorecard</Link></Button> : null },
          ]} />
      </Panel>
      {open && <NewInterview open={open} onClose={() => setOpen(false)} />}
    </>
  )
}
