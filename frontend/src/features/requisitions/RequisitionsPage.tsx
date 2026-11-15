import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { Briefcase, MapPin, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { DataTable } from '@/components/app/data-table'
import { StatusCards } from '@/components/app/status-cards'
import { PageHeader, Panel, Tag } from '@/components/app/page'
import { EmptyState, ErrorAlert } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { apiV1RequisitionsList, useApiV1RequisitionsCreate } from '@/shared/api/generated/requisitions/requisitions'
import { useAllPages } from '@/shared/hooks/useAllPages'
import type { Requisition } from '@/shared/api/generated/model'
import { useMe } from '@/shared/hooks/useMe'
import { relativeTime } from '@/shared/ui/common'
import { RequisitionForm, emptyRequisition } from './RequisitionForm'

export function JobMark({ title }: { title: string }) {
  return (
    <span className="bg-brand-soft grid size-10 shrink-0 place-items-center rounded-xl text-violet ring-1 ring-violet/30 ring-inset">
      <Briefcase className="size-[18px]" /><span className="sr-only">{title}</span>
    </span>
  )
}

const VIEWS = [['all', 'All'], ['approved', 'Open'], ['submitted', 'Waiting for HR'], ['draft', 'Draft'], ['rejected', 'Rejected'], ['closed', 'Closed']]

export function RequisitionsPage() {
  const navigate = useNavigate()
  const [params, setParams] = useSearchParams()
  const { hasRole } = useMe()
  const canCreate = hasRole('hr_admin', 'recruiter', 'hiring_manager')
  const open = params.get('new') === '1'
  const setOpen = (on: boolean) => setParams(on ? { new: '1' } : {}, { replace: true })
  const list = useAllPages(['requisitions'], (page) => apiV1RequisitionsList({ page }))
  const create = useApiV1RequisitionsCreate()
  const all = list.data?.results ?? []
  const [view, setView] = useState('all')
  const shown = view === 'all' ? all : all.filter((r) => r.status === view)

  return (
    <>
      <PageHeader title="Jobs" crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Jobs' }]}
        description="Requests to hire. HR approves each one before candidates are matched against it."
        actions={canCreate && <Button onClick={() => setOpen(true)}><Plus /> New job</Button>} />
      <StatusCards items={VIEWS.map(([value, label]) => ({ value, label, count: value === 'all' ? all.length : all.filter((r) => r.status === value).length }))} value={view} onChange={setView} />
      <ErrorAlert error={list.error} />
      <Panel flush className="overflow-hidden">
        <DataTable rows={shown} rowKey={(r) => r.id} noun="jobs" loading={list.isLoading} onOpen={(r) => navigate(`/requisitions/${r.id}`)}
          filterText={(r) => `${r.title} ${r.department} ${r.location} ${(r.must_have_skills ?? []).join(' ')}`}
          filterPlaceholder="Search title, team or skill" initialSort={{ key: 'created', desc: true }} exportName="jobs"
          facets={[
            { key: 'department', label: 'Department', value: (r) => r.department, format: (v) => v },
            { key: 'location', label: 'Location', value: (r) => r.location || null, format: (v) => v },
            { key: 'type', label: 'Type', value: (r) => r.employment_type },
          ]}
          empty={<EmptyState title="No jobs yet" icon={<Briefcase />} action={canCreate && <Button onClick={() => setOpen(true)}><Plus /> Create the first job</Button>}>
            Jobs you create or are assigned to appear here.</EmptyState>}
          columns={[
            { key: 'title', header: 'Job', sort: (r: Requisition) => r.title, csv: (r: Requisition) => r.title, cell: (r: Requisition) => (
              <div className="flex items-center gap-3">
                <JobMark title={r.title} />
                <div className="min-w-0">
                  <p className="truncate font-semibold">{r.title}</p>
                  <div className="mt-1 flex flex-wrap gap-1">{(r.must_have_skills ?? []).slice(0, 3).map((s) => <Tag key={s}>{s}</Tag>)}
                    {(r.must_have_skills ?? []).length > 3 && <span className="text-xs text-muted-foreground">+{(r.must_have_skills ?? []).length - 3}</span>}</div>
                </div>
              </div>
            ) },
            { key: 'department', header: 'Department', hide: 'sm', sort: (r: Requisition) => r.department, cell: (r: Requisition) => r.department },
            { key: 'location', header: 'Location', hide: 'md', sort: (r: Requisition) => r.location ?? '', cell: (r: Requisition) => r.location
              ? <span className="flex items-center gap-1.5 text-foreground/85"><MapPin className="size-3.5 text-muted-foreground" />{r.location}</span> : <span className="text-muted-foreground">—</span> },
            { key: 'level', header: 'Level', hide: 'lg', sort: (r: Requisition) => r.level ?? '', cell: (r: Requisition) => r.level || '—' },
            { key: 'headcount', header: 'Openings', align: 'right', sort: (r: Requisition) => r.headcount ?? 0, cell: (r: Requisition) => <span className="tabular font-semibold">{r.headcount}</span> },
            { key: 'status', header: 'Status', sort: (r: Requisition) => r.status, cell: (r: Requisition) => <StatusBadge value={r.status} /> },
            { key: 'created', header: 'Created', hide: 'lg', sort: (r: Requisition) => r.created_at, cell: (r: Requisition) => <span className="text-muted-foreground">{relativeTime(r.created_at)}</span> },
          ]} />
      </Panel>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-h-[92svh] overflow-y-auto sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle className="font-heading text-xl">New job</DialogTitle>
            <DialogDescription>Saved as a draft. Submit it for HR approval when it is ready.</DialogDescription>
          </DialogHeader>
          <ErrorAlert error={create.error} />
          <RequisitionForm initial={emptyRequisition} submitLabel="Create draft" busy={create.isPending} onCancel={() => setOpen(false)}
            onSubmit={(values) => create.mutate({ data: values }, { onSuccess: (created) => navigate(`/requisitions/${created.id}`) })} />
        </DialogContent>
      </Dialog>
    </>
  )
}
