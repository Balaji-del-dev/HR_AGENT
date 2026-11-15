import { type DragEvent, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'
import { ClipboardCheck, GripVertical, MoreHorizontal } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ReasonDialog } from '@/components/app/dialogs'
import { PageHeader } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import { ErrorAlert, PageSkeleton } from '@/components/app/states'
import { useSession } from '@/app/session'
import { useApiV1ApplicationsDecisionsCreate } from '@/shared/api/generated/applications/applications'
import type { Application, StageEnum } from '@/shared/api/generated/model'
import { useApiV1RequisitionsApplicationsList, useApiV1RequisitionsRetrieve } from '@/shared/api/generated/requisitions/requisitions'
import { relativeTime } from '@/shared/ui/common'

const COLUMNS: StageEnum[] = ['applied', 'screening', 'shortlisted', 'interview', 'offer', 'hired', 'rejected']
const ACCENT: Record<string, string> = {
  applied: 'bg-sky-500', screening: 'bg-cyan-500', shortlisted: 'bg-indigo-500', interview: 'bg-violet-500', offer: 'bg-amber-500', hired: 'bg-emerald-500', rejected: 'bg-slate-400',
}
type Move = { application: Application; to: StageEnum }

/** Kanban by stage. Every move, by drag or menu, asks for a reason and is recorded with your name. */
export function PipelineBoardPage() {
  const { id = '' } = useParams()
  const { t } = useTranslation()
  const blind = useSession((s) => s.blindReview)
  const requisition = useApiV1RequisitionsRetrieve(id)
  const applications = useApiV1RequisitionsApplicationsList(id)
  const decide = useApiV1ApplicationsDecisionsCreate()
  const [move, setMove] = useState<Move | null>(null)
  const [over, setOver] = useState<string | null>(null)
  const label = (s: string) => t(`stage.${s}`, { defaultValue: s })

  const confirm = (reason: string) => {
    if (!move) return
    const decision = move.to === 'rejected' ? 'reject' : 'advance'
    decide.mutate({ id: move.application.id, data: { decision, reason, ...(decision === 'advance' ? { to_stage: move.to } : {}) } },
      { onSuccess: () => toast.success(`Moved to ${label(move.to)}`), onSettled: () => setMove(null) })
  }
  const onDrop = (event: DragEvent, to: StageEnum) => {
    setOver(null)
    const application = applications.data?.find((a) => a.id === event.dataTransfer.getData('text/plain'))
    if (application && application.stage !== to) setMove({ application, to })
  }
  if (applications.isLoading) return <PageSkeleton />
  const name = (a: Application, i: number) => blind ? `Candidate ${i + 1}` : a.candidate_name

  return (
    <>
      <PageHeader title="Pipeline" crumbs={[{ label: 'Jobs', to: '/requisitions' }, { label: requisition.data?.title ?? 'Job', to: `/requisitions/${id}` }, { label: 'Pipeline' }]}
        description="Drag a card to another stage, or use its menu. Each move asks for a reason and goes in the audit trail."
        actions={<Button variant="outline" asChild><Link to={`/requisitions/${id}/review`}><ClipboardCheck /> Screening</Link></Button>} />
      <ErrorAlert error={decide.error ?? applications.error} />
      <div className="grid auto-cols-[minmax(200px,1fr)] grid-flow-col gap-4 overflow-x-auto pb-3">
        {COLUMNS.map((stage) => {
          const cards = (applications.data ?? []).filter((a) => a.stage === stage)
          return (
            <section key={stage} aria-label={`${label(stage)} column`}
              onDragOver={(e) => { e.preventDefault(); setOver(stage) }} onDragLeave={() => setOver(null)} onDrop={(e) => onDrop(e, stage)}
              className={cn('flex min-h-[440px] flex-col rounded-xl border bg-muted/50 transition', over === stage && 'border-primary/60 bg-primary/5')}>
              <div className={cn('h-1 rounded-t-xl', ACCENT[stage])} />
              <header className="flex items-center gap-2 px-4 pt-3 pb-2">
                <h2 className="font-heading flex-1 text-[15px] font-semibold capitalize">{label(stage)}</h2>
                <span className="tabular rounded-full bg-foreground/8 px-2 py-0.5 text-xs font-semibold">{cards.length}</span>
              </header>
              <ul className="flex flex-1 flex-col gap-2 px-2.5 pb-3">
                {cards.length === 0 && <li className="m-1 flex flex-1 items-center justify-center rounded-xl border border-dashed text-xs text-muted-foreground">Drop here</li>}
                {cards.map((application, index) => (
                  <li key={application.id} draggable onDragStart={(e) => e.dataTransfer.setData('text/plain', application.id)}
                    className="group cursor-grab rounded-lg border bg-card p-3 shadow-xs transition hover:-translate-y-0.5 hover:border-primary/40 active:cursor-grabbing">
                    <div className="flex items-start gap-2.5">
                      <PersonAvatar name={blind ? application.id : application.candidate_name} size={34} />
                      <div className="min-w-0 flex-1">
                        <Link to={`/candidates/${application.candidate_id}`} className="block text-sm leading-snug font-semibold text-foreground hover:text-primary">{name(application, index)}</Link>
                        <p className="mt-0.5 text-xs text-muted-foreground"><span className="capitalize">{(application.source || 'applied').replaceAll('_', ' ')}</span> · <span className="whitespace-nowrap">{relativeTime(application.stage_changed_at ?? application.created_at)}</span></p>
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="size-7 opacity-60 group-hover:opacity-100" aria-label={`Move ${name(application, index)}`}><MoreHorizontal /></Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end" className="w-44">
                          <DropdownMenuLabel>Move to</DropdownMenuLabel>
                          <DropdownMenuSeparator />
                          {COLUMNS.filter((s) => s !== stage).map((s) => (
                            <DropdownMenuItem key={s} onClick={() => setMove({ application, to: s })} className={cn('capitalize', s === 'rejected' && 'text-destructive')}>{label(s)}</DropdownMenuItem>
                          ))}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                    <GripVertical className="mx-auto mt-1 size-3.5 rotate-90 text-muted-foreground/40" aria-hidden />
                  </li>
                ))}
              </ul>
            </section>
          )
        })}
      </div>
      <ReasonDialog open={Boolean(move)} onClose={() => setMove(null)} onConfirm={confirm} destructive={move?.to === 'rejected'}
        title={move ? `Move ${blind ? 'this candidate' : move.application.candidate_name} to ${label(move.to)}` : ''}
        description="The reason is stored with the decision and shown in the audit trail. It is never shown to the candidate."
        confirmLabel={move?.to === 'rejected' ? 'Reject' : 'Move'} />
    </>
  )
}
