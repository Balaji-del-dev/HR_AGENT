import { useState } from 'react'
import { Link } from 'react-router'
import { motion } from 'motion/react'
import { ArrowRight, Bot, ClipboardCheck, UserRound } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { PageHeader, Panel } from '@/components/app/page'
import { EmptyState, ErrorAlert, SkeletonRows } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { useApiV1ApprovalsList } from '@/shared/api/generated/approvals/approvals'
import type { ApiV1ApprovalsListStatus } from '@/shared/api/generated/model'
import { relativeTime } from '@/shared/ui/common'
import { KIND_ICON, KIND_TINT } from '@/components/app/kinds'

export function ApprovalsPage() {
  const [status, setStatus] = useState('pending')
  const approvals = useApiV1ApprovalsList(status !== 'all' ? { status: status as ApiV1ApprovalsListStatus } : undefined)
  const rows = approvals.data?.results ?? []
  const mine = rows.filter((a) => a.can_decide)
  const others = rows.filter((a) => !a.can_decide)
  const group = (title: string, items: typeof rows) => items.length > 0 && (
    <section className="space-y-2">
      <h2 className="px-1 text-xs font-semibold tracking-wide text-muted-foreground uppercase">{title} · {items.length}</h2>
      <ul className="space-y-2">
        {items.map((a, i) => (
          <motion.li key={a.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: Math.min(i * 0.03, 0.3) }}>
            <Link to={`/approvals/${a.id}`} className={cn('glass group relative flex items-center gap-4 overflow-hidden rounded-xl px-4 py-3.5 transition hover:-translate-y-px hover:border-primary/40 focus-visible:ring-2 focus-visible:ring-ring outline-none',
              a.can_decide && a.status === 'pending' && 'before:bg-brand before:absolute before:inset-y-0 before:left-0 before:w-1')}>
              <span className={cn('grid size-10 shrink-0 place-items-center rounded-xl [&_svg]:size-5', KIND_TINT[a.kind] ?? 'bg-primary/15 text-violet')}>{KIND_ICON[a.kind] ?? <ClipboardCheck />}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate font-semibold">{a.title}</span>
                <span className="flex items-center gap-1.5 truncate text-[13px] text-muted-foreground">
                  {a.agent_run_id ? <Bot className="size-3.5" /> : <UserRound className="size-3.5" />}
                  <span className="capitalize">{a.kind.replaceAll('_', ' ')}</span><span aria-hidden>·</span>{a.summary}
                </span>
              </span>
              <span className="hidden text-xs text-muted-foreground sm:inline">{relativeTime(a.created_at)}</span>
              <StatusBadge value={a.status} />
              <ArrowRight className="size-4 text-muted-foreground transition group-hover:translate-x-0.5 group-hover:text-violet" />
            </Link>
          </motion.li>
        ))}
      </ul>
    </section>
  )
  return (
    <>
      <PageHeader crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Approvals' }]} title="Approvals"
        description="Drafts from agents and colleagues. Only the named roles can decide, and every decision is recorded with a reason." />
      <Tabs value={status} onValueChange={setStatus} className="mb-5">
        <TabsList>
          <TabsTrigger value="pending">Pending{mine.length && status === 'pending' ? ` · ${mine.length} for you` : ''}</TabsTrigger>
          <TabsTrigger value="approved">Approved</TabsTrigger><TabsTrigger value="rejected">Rejected</TabsTrigger>
          <TabsTrigger value="changes_requested">Changes requested</TabsTrigger><TabsTrigger value="all">All</TabsTrigger>
        </TabsList>
      </Tabs>
      <ErrorAlert error={approvals.error} />
      {approvals.isLoading ? <Panel><SkeletonRows /></Panel> : rows.length === 0 ? (
        <Panel><EmptyState icon={<ClipboardCheck />} title={status === 'pending' ? 'Inbox zero' : 'Nothing here'}>{status === 'pending' ? 'No drafts are waiting for a decision.' : 'No approvals with this status.'}</EmptyState></Panel>
      ) : (
        <div className="space-y-6">{group(status === 'pending' ? 'Your turn' : 'Yours to see', mine)}{group(status === 'pending' ? 'Waiting on others' : 'Others', others)}</div>
      )}
    </>
  )
}
