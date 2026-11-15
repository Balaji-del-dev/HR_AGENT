import { useState } from 'react'
import { useNavigate } from 'react-router'
import { GitCompareArrows, Plus, Sparkles } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { DataTable } from '@/components/app/data-table'
import { StatusCards } from '@/components/app/status-cards'
import { PageHeader, Panel, Tag } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import { EmptyState, ErrorAlert } from '@/components/app/states'
import { useSession } from '@/app/session'
import { apiV1CandidatesList, useApiV1CandidatesCreate } from '@/shared/api/generated/candidates/candidates'
import { useAllPages } from '@/shared/hooks/useAllPages'
import type { Candidate } from '@/shared/api/generated/model'
import { useMe } from '@/shared/hooks/useMe'
import { relativeTime } from '@/shared/ui/common'

export function CandidatesPage() {
  const navigate = useNavigate()
  const { hasRole } = useMe()
  const blind = useSession((s) => s.blindReview)
  const [skill, setSkill] = useState('')
  const [picked, setPicked] = useState<string[]>([])
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ full_name: '', email: '', phone: '', application_consent: true, talent_pool_consent: false })
  const list = useAllPages(['candidates', skill], (page) => apiV1CandidatesList({ ...(skill ? { q: skill } : {}), page }))
  const create = useApiV1CandidatesCreate()
  const all = list.data?.results ?? []
  const [view, setView] = useState('all')
  const rows = all.filter((c) => view === 'all' || (view === 'pool' ? c.in_talent_pool : !c.in_talent_pool))
  const toggle = (id: string) => setPicked((p) => p.includes(id) ? p.filter((x) => x !== id) : [...p, id].slice(-3))

  return (
    <>
      <PageHeader title="Candidates" crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Candidates' }]}
        description="Everyone who applied or agreed to join your talent pool. Pick up to three to compare side by side."
        actions={<>
          {picked.length >= 2 && <Button variant="outline" onClick={() => navigate(`/candidates/compare?ids=${picked.join(',')}`)}><GitCompareArrows /> Compare {picked.length}</Button>}
          {hasRole('hr_admin', 'recruiter') && <Button onClick={() => setOpen(true)}><Plus /> Add candidate</Button>}
        </>} />
      <StatusCards items={[
        { value: 'all', label: 'All', count: all.length },
        { value: 'pool', label: 'In talent pool', count: all.filter((c) => c.in_talent_pool).length },
        { value: 'applicants', label: 'Applicants only', count: all.filter((c) => !c.in_talent_pool).length },
      ]} value={view} onChange={setView} />
      <ErrorAlert error={list.error} />
      <Panel flush className="overflow-hidden">
        <DataTable rows={rows} rowKey={(c) => c.id} noun="candidates" loading={list.isLoading} onOpen={(c) => navigate(`/candidates/${c.id}`)}
          filterText={(c) => `${c.full_name} ${c.email} ${c.source}`} filterPlaceholder="Search name or email" initialSort={{ key: 'added', desc: true }} exportName="candidates"
          facets={[
            { key: 'source', label: 'Source', value: (c) => c.source || null },
          ]}
          toolbar={<>
            <div className="relative"><Sparkles className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-violet" />
              <Input value={skill} onChange={(e) => setSkill(e.target.value)} placeholder="Has skill, e.g. FastAPI" aria-label="Filter by skill" className="h-9 w-52 pl-9" /></div>
          </>}
          empty={<EmptyState title="No candidates match" action={hasRole('hr_admin', 'recruiter') && <Button variant="outline" onClick={() => setOpen(true)}>Add a candidate</Button>}>Import applicants on a job, or try another skill.</EmptyState>}
          columns={[
            { key: 'pick', header: '', className: 'w-10', cell: (c: Candidate) => (
              <span onClick={(e) => e.stopPropagation()}><Checkbox checked={picked.includes(c.id)} onCheckedChange={() => toggle(c.id)} aria-label={`Select ${c.full_name} to compare`} /></span>
            ) },
            { key: 'name', header: 'Candidate', sort: (c: Candidate) => c.full_name, cell: (c: Candidate) => (
              <div className="flex items-center gap-3">
                <PersonAvatar name={blind ? c.id : c.full_name} size={34} />
                <div className="min-w-0"><p className="truncate font-medium">{blind ? `Candidate ${c.id.slice(0, 4).toUpperCase()}` : c.full_name}</p>
                  <p className="truncate text-xs text-muted-foreground">{blind ? 'Identity hidden' : c.email || 'No email on file'}</p></div>
              </div>
            ) },
            { key: 'source', header: 'Source', hide: 'sm', sort: (c: Candidate) => c.source ?? '', cell: (c: Candidate) => <Tag className="capitalize">{(c.source ?? '').replaceAll('_', ' ')}</Tag> },
            { key: 'pool', header: 'Talent pool', hide: 'md', sort: (c: Candidate) => Number(c.in_talent_pool), cell: (c: Candidate) => c.in_talent_pool ? <Tag tone="success">Consented</Tag> : <span className="text-muted-foreground">—</span> },
            { key: 'added', header: 'Added', hide: 'md', sort: (c: Candidate) => c.created_at, cell: (c: Candidate) => <span className="text-muted-foreground">{relativeTime(c.created_at)}</span> },
          ]} />
      </Panel>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <DialogHeader><DialogTitle className="font-heading">Add a candidate</DialogTitle>
            <DialogDescription>We only store people who agreed to it. Record their consent below.</DialogDescription></DialogHeader>
          <ErrorAlert error={create.error} />
          <div className="grid gap-4">
            {(['full_name', 'email', 'phone'] as const).map((f) => (
              <div key={f} className="grid gap-2"><Label htmlFor={f}>{f === 'full_name' ? 'Full name' : f[0].toUpperCase() + f.slice(1)}</Label>
                <Input id={f} value={form[f]} onChange={(e) => setForm({ ...form, [f]: e.target.value })} /></div>
            ))}
            <label className="flex items-center gap-2 text-sm"><Checkbox checked={form.application_consent} onCheckedChange={(v) => setForm({ ...form, application_consent: v === true })} /> Agreed to be considered for this application</label>
            <label className="flex items-center gap-2 text-sm"><Checkbox checked={form.talent_pool_consent} onCheckedChange={(v) => setForm({ ...form, talent_pool_consent: v === true })} /> Agreed to join the talent pool</label>
          </div>
          <DialogFooter>
            <Button variant="ghost" onClick={() => setOpen(false)}>Cancel</Button>
            <Button disabled={!form.full_name.trim() || create.isPending} onClick={() => create.mutate({ data: form }, { onSuccess: (c) => { setOpen(false); navigate(`/candidates/${c.id}`) } })}>Add candidate</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
