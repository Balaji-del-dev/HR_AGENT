import { Link } from 'react-router'
import { motion } from 'motion/react'
import { Bot, CircleCheck, Hourglass, Loader2, ShieldCheck, UserCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { useRunEvents } from '@/shared/hooks/useRunEvents'
import { StatusBadge } from './status'

export const NODE_LABELS: Record<string, string> = {
  guard_input: 'Checked the input for prompt injection', supervisor: 'Picked the agent for this job',
  requisition_review: 'Reviewed the requisition', job_jd: 'Drafted the job description', sourcing: 'Searched applicants and talent pool',
  resume_parsing: 'Read and structured the resume', candidates: 'Compared each candidate to every criterion', comms: 'Drafted the email',
  scheduling: 'Found times the whole panel is free', feedback: 'Summarised the scorecards', offer: 'Drafted an offer inside the band',
  assistant: 'Searched and answered', analytics: 'Ran the report', compliance: 'Checked for biased wording',
  output_checks: 'Checked the output for contact details and protected attributes', open_review: 'Opened an approval for you',
  human_review: 'Waiting for a person to decide', apply_decision: 'Applied the decision', audit: 'Wrote the audit record',
}

function nodeIcon(node: string) {
  if (node === 'guard_input' || node === 'output_checks') return <ShieldCheck className="size-3.5" />
  if (node === 'human_review' || node === 'open_review') return <Hourglass className="size-3.5" />
  if (node === 'apply_decision') return <UserCheck className="size-3.5" />
  if (node === 'audit') return <CircleCheck className="size-3.5" />
  return <Bot className="size-3.5" />
}

/** Live view of one agent run. When it pauses, it says plainly that nothing happens until a person decides. */
export function RunProgress({ runId, title = 'Agent run', compact }: { runId: string; title?: string; compact?: boolean }) {
  const { run, connected } = useRunEvents(runId)
  if (!run) return <div className="glass rounded-2xl p-4"><Progress value={30} className="h-1" /></div>
  const active = run.status === 'queued' || run.status === 'running'
  const steps = 'steps' in run ? [...run.steps] : []
  const interrupt = run.pending_interrupt as { approval_request_id?: string } | null
  return (
    <div className="glass rounded-2xl p-4" aria-live="polite">
      <div className="mb-3 flex items-center gap-2">
        <span className="grid size-7 place-items-center rounded-lg bg-primary/15 text-violet">{active ? <Loader2 className="size-4 animate-spin" /> : <Bot className="size-4" />}</span>
        <p className="font-heading flex-1 text-[15px] font-semibold">{title}</p>
        <StatusBadge value={run.status} />
        <span className="text-xs text-muted-foreground">{connected ? 'live' : 'polling'}</span>
      </div>
      {!compact && (
        <ol className="space-y-1.5">
          {steps.map((step, i) => (
            <motion.li key={step.sequence} initial={{ opacity: 0, x: -6 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: Math.min(i * 0.04, 0.4) }}
              className="flex items-center gap-2 text-[13px]">
              <span className="text-muted-foreground">{nodeIcon(step.node)}</span>
              <span>{NODE_LABELS[step.node] ?? step.node.replaceAll('_', ' ')}</span>
            </motion.li>
          ))}
        </ol>
      )}
      {run.status === 'awaiting_review' && interrupt?.approval_request_id && (
        <div className="mt-3 flex items-center gap-3 rounded-xl bg-warning/10 p-3 text-[13px]">
          <Hourglass className="size-4 shrink-0 text-warning" />
          <p className="flex-1">The agent prepared a draft. Nothing happens until a person approves it.</p>
          <Button size="sm" asChild><Link to={`/approvals/${interrupt.approval_request_id}`}>Review now</Link></Button>
        </div>
      )}
      {run.error && <p className="mt-3 rounded-xl bg-destructive/10 p-3 text-[13px] text-destructive">{run.error}</p>}
      <div className="mt-3"><Button variant="link" size="sm" className="h-auto p-0" asChild><Link to={`/agents/${run.id}`}>Open in agent monitor →</Link></Button></div>
    </div>
  )
}
