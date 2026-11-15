import { useState } from 'react'
import { toast } from 'sonner'
import { CalendarDays, Clock, Percent, Send, Wallet } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { DataTable } from '@/components/app/data-table'
import { StatusCards } from '@/components/app/status-cards'
import { FactList } from '@/components/app/detail'
import { PageHeader, Panel } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import { EmptyState, ErrorAlert } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { Timeline } from '@/components/app/timeline'
import { apiV1OffersList, useApiV1OffersOutcomeCreate, useApiV1OffersSubmitCreate } from '@/shared/api/generated/offers/offers'
import { useAllPages } from '@/shared/hooks/useAllPages'
import type { Offer, OutcomeInStatusEnum } from '@/shared/api/generated/model'
import { useMe } from '@/shared/hooks/useMe'
import { money, shortDate } from '@/shared/ui/common'

function bandPosition(o: Offer) {
  return Math.min(100, Math.max(0, (Number(o.base_salary) - Number(o.band_min)) / Math.max(1, Number(o.band_max) - Number(o.band_min)) * 100))
}

/** Where the salary sits inside the approved band. */
function BandBar({ offer, large }: { offer: Offer; large?: boolean }) {
  const pos = bandPosition(offer)
  return (
    <div className={cn(large ? 'mt-2' : 'mt-1.5 w-40')} aria-label={`At ${Math.round(pos)}% of the band`}>
      <div className={cn('relative rounded-full bg-foreground/8', large ? 'h-2.5' : 'h-1.5')}>
        <div className="bg-brand absolute inset-y-0 left-0 rounded-full opacity-80" style={{ width: `${pos}%` }} />
        <span className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-background bg-white" style={{ left: `${pos}%` }} />
      </div>
      {large && <div className="mt-1.5 flex justify-between text-xs text-muted-foreground tabular"><span>{money(offer.band_min, offer.currency)}</span><span>{money(offer.band_max, offer.currency)}</span></div>}
    </div>
  )
}

function Chain({ offer }: { offer: Offer }) {
  const approvals = offer.status_history.filter((h) => h.to_status === 'approved').length
  const steps = [
    { label: 'HR', done: ['approved', 'sent', 'accepted', 'declined'].includes(offer.status) || (offer.status === 'pending_approval' && approvals > 0) },
    { label: 'Finance', done: ['approved', 'sent', 'accepted', 'declined'].includes(offer.status) },
  ]
  return (
    <span className="flex items-center gap-1.5">
      {steps.map((s, i) => (
        <span key={s.label} className="flex items-center gap-1.5">
          {i > 0 && <span className={cn('h-px w-4', s.done ? 'bg-success' : 'bg-border')} />}
          <span className={cn('rounded-md px-1.5 py-0.5 text-xs font-semibold ring-1 ring-inset',
            s.done ? 'bg-success/12 text-success ring-success/30' : offer.status === 'pending_approval' ? 'bg-warning/12 text-warning ring-warning/30' : 'bg-muted text-muted-foreground ring-border')}>{s.label}</span>
        </span>
      ))}
    </span>
  )
}

function OfferActions({ offer }: { offer: Offer }) {
  const { hasRole } = useMe()
  const submit = useApiV1OffersSubmitCreate()
  const outcome = useApiV1OffersOutcomeCreate()
  if (!hasRole('hr_admin', 'recruiter')) return null
  return (
    <span className="flex justify-end" onClick={(e) => e.stopPropagation()}>
      {offer.status === 'draft' && <Button size="sm" variant="outline" disabled={submit.isPending} onClick={() => submit.mutate({ id: offer.id }, { onSuccess: () => toast.success('Sent for approval') })}><Send /> Submit</Button>}
      {(offer.status === 'approved' || offer.status === 'sent') && (
        <Select onValueChange={(v) => outcome.mutate({ id: offer.id, data: { status: v as OutcomeInStatusEnum } }, { onSuccess: () => toast.success(`Recorded: ${v}`) })}>
          <SelectTrigger size="sm" className="w-36" aria-label="Record outcome"><SelectValue placeholder="Record outcome" /></SelectTrigger>
          <SelectContent>{(offer.status === 'approved' ? ['sent', 'withdrawn'] : ['accepted', 'declined', 'withdrawn']).map((st) => <SelectItem key={st} value={st} className="capitalize">{st}</SelectItem>)}</SelectContent>
        </Select>
      )}
    </span>
  )
}

export function OffersPage() {
  const offers = useAllPages(['offers'], (page) => apiV1OffersList({ page }))
  const [openId, setOpenId] = useState<string | null>(null)
  const [view, setView] = useState('all')
  const all = offers.data?.results ?? []
  const shown = view === 'all' ? all : all.filter((o) => o.status === view)
  const open = all.find((o) => o.id === openId)
  return (
    <>
      <PageHeader title="Offers" crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Offers' }]}
        description="Drafted inside the approved pay band. HR approves, then finance, then a recruiter sends it." />
      <StatusCards items={[['all', 'All'], ['draft', 'Draft'], ['pending_approval', 'In approval'], ['approved', 'Ready to send'], ['sent', 'Sent'], ['accepted', 'Accepted'], ['declined', 'Declined']].map(([value, label]) => ({ value, label, count: value === 'all' ? all.length : all.filter((o) => o.status === value).length }))} value={view} onChange={setView} />
      <ErrorAlert error={offers.error} />
      <Panel flush className="overflow-hidden">
        <DataTable rows={shown} rowKey={(o) => o.id} noun="offers" loading={offers.isLoading} onOpen={(o) => setOpenId(o.id)} activeKey={openId} exportName="offers"
          filterText={(o) => `${o.candidate_name} ${o.title} ${o.status}`} filterPlaceholder="Search candidate or role" initialSort={{ key: 'created', desc: true }}
          facets={[{ key: 'role', label: 'Role', value: (o) => o.title, format: (v) => v }]}
          empty={<EmptyState title="No offers yet" icon={<Wallet />}>Start one from a candidate in the interview stage with “Draft offer”.</EmptyState>}
          columns={[
            { key: 'candidate', header: 'Candidate', sort: (o: Offer) => o.candidate_name, cell: (o: Offer) => (
              <div className="flex items-center gap-3"><PersonAvatar name={o.candidate_name} size={36} />
                <div className="min-w-0"><p className="truncate font-semibold">{o.candidate_name}</p><p className="truncate text-xs text-muted-foreground">{o.title}</p></div></div>
            ) },
            { key: 'base', header: 'Base salary', sort: (o: Offer) => Number(o.base_salary), csv: (o: Offer) => o.base_salary, cell: (o: Offer) => (
              <div><p className="tabular font-semibold">{money(o.base_salary, o.currency)}</p><BandBar offer={o} /></div>
            ) },
            { key: 'chain', header: 'Approvals', hide: 'md', cell: (o: Offer) => <Chain offer={o} /> },
            { key: 'start', header: 'Start', hide: 'lg', sort: (o: Offer) => o.start_date ?? '', cell: (o: Offer) => <span className="text-muted-foreground">{o.start_date ?? 'TBC'}</span> },
            { key: 'status', header: 'Status', sort: (o: Offer) => o.status, cell: (o: Offer) => <StatusBadge value={o.status} /> },
            { key: 'created', header: 'Drafted', hide: 'lg', sort: (o: Offer) => o.created_at, cell: (o: Offer) => <span className="text-muted-foreground">{shortDate(o.created_at)}</span> },
            { key: 'action', header: '', hideable: false, align: 'right', cell: (o: Offer) => <OfferActions offer={o} /> },
          ]} />
      </Panel>
      <Sheet open={Boolean(open)} onOpenChange={(o) => !o && setOpenId(null)}>
        <SheetContent side="right" className="w-full overflow-y-auto sm:max-w-md">
          {open && (
            <>
              <SheetHeader className="border-b pb-5">
                <div className="flex items-center gap-3">
                  <PersonAvatar name={open.candidate_name} size={52} />
                  <div className="min-w-0">
                    <SheetTitle className="font-heading text-xl">{open.candidate_name}</SheetTitle>
                    <SheetDescription>{open.title}</SheetDescription>
                  </div>
                </div>
                <div className="mt-3 flex items-center gap-2"><StatusBadge value={open.status} /><Chain offer={open} /></div>
              </SheetHeader>
              <div className="space-y-6 px-4 pb-6">
                <div>
                  <p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">Base salary</p>
                  <p className="mt-1 text-3xl font-semibold tabular">{money(open.base_salary, open.currency)}</p>
                  <BandBar offer={open} large />
                </div>
                <FactList items={[
                  { icon: <Percent />, label: 'Bonus', value: open.bonus_percent ? `${open.bonus_percent}%` : '—' },
                  { icon: <CalendarDays />, label: 'Start date', value: open.start_date ?? 'TBC' },
                  { icon: <Clock />, label: 'Drafted', value: shortDate(open.created_at) },
                ]} />
                {open.rationale && (
                  <div>
                    <p className="mb-1.5 text-xs font-semibold tracking-wide text-muted-foreground uppercase">Why this number</p>
                    <p className="rounded-xl border bg-muted/50 p-3 text-sm leading-relaxed">{open.rationale}</p>
                  </div>
                )}
                <div>
                  <p className="mb-3 text-xs font-semibold tracking-wide text-muted-foreground uppercase">History</p>
                  {open.status_history.length === 0 ? <p className="text-sm text-muted-foreground">No changes yet.</p> : (
                    <Timeline dense items={open.status_history.map((h, i) => ({
                      id: `${h.created_at}-${i}`, title: <span className="capitalize">{h.from_status.replaceAll('_', ' ')} → {h.to_status.replaceAll('_', ' ')}</span>,
                      detail: h.reason || undefined, time: shortDate(h.created_at),
                      tone: h.to_status === 'approved' || h.to_status === 'accepted' ? 'success' : h.to_status === 'rejected' || h.to_status === 'declined' ? 'destructive' : 'primary',
                    }))} />
                  )}
                </div>
                <OfferActions offer={open} />
              </div>
            </>
          )}
        </SheetContent>
      </Sheet>
    </>
  )
}
