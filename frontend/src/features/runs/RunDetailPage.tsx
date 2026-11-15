import type { ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { Bot, Clock, Coins, ShieldAlert, Wrench } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import { CopyButton } from '@/components/app/dialogs'
import { DetailHero } from '@/components/app/detail'
import { KeyValue, Panel } from '@/components/app/page'
import { NODE_LABELS } from '@/components/app/run-progress'
import { StatTile } from '@/components/app/stat'
import { EmptyState, PageSkeleton } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { Timeline } from '@/components/app/timeline'
import { useRunEvents } from '@/shared/hooks/useRunEvents'
import { shortDate } from '@/shared/ui/common'
import { AgentGraph, GraphLegend } from '../agents/AgentGraph'

type Call = { id: string; tool: string; agent: string; status: string; policy_reason: string; duration_ms: number; error: string; result_summary: Record<string, unknown> }

export function RunDetailPage() {
  const { id = '' } = useParams()
  const { run, connected } = useRunEvents(id)
  if (!run) return <PageSkeleton />
  const steps = 'steps' in run ? [...run.steps] : []
  const calls = ('tool_calls' in run ? [...run.tool_calls] : []) as unknown as Call[]
  const denied = calls.filter((c) => c.status === 'denied').length
  const active = run.status === 'queued' || run.status === 'running'
  const interrupt = run.pending_interrupt as { approval_request_id?: string } | null
  const seconds = run.started_at && run.finished_at ? Math.max(0, (new Date(run.finished_at).getTime() - new Date(run.started_at).getTime()) / 1000) : null

  return (
    <>
      <DetailHero crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Agent monitor', to: '/agents' }, { label: run.kind.replaceAll('_', ' ') }]}
        avatar={<span className="bg-brand grid size-14 place-items-center rounded-xl text-white"><Bot className="size-7" /></span>}
        eyebrow={`Agent run · ${run.id.slice(0, 8)}`} title={<span className="capitalize">{run.kind.replaceAll('_', ' ')}</span>}
        badges={<><StatusBadge value={run.status} /><span className="flex items-center gap-1.5 text-xs text-muted-foreground"><span className={connected ? 'size-2 rounded-full bg-success pulse-ring text-success' : 'size-2 rounded-full bg-muted-foreground'} />{connected ? 'live' : 'polling'}</span></>}
        subtitle={`Started ${shortDate(run.started_at ?? run.created_at)} · model ${run.model_name} · graph ${run.graph_version}`}
        actions={run.status === 'awaiting_review' && interrupt?.approval_request_id && <Button asChild><Link to={`/approvals/${interrupt.approval_request_id}`}>Review the draft</Link></Button>} />
      {active && <Progress value={60} className="mb-4 h-1" />}
      {run.error && <p className="mb-4 rounded-xl bg-destructive/10 px-4 py-3 text-sm text-destructive">{run.error}</p>}
      <div className="mb-6 grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatTile label="Tool calls" value={calls.length} icon={<Wrench />} hint={`${denied} denied by policy`} tone={denied ? 'destructive' : 'primary'} />
        <StatTile label="Tokens" value={(run.tokens_in + run.tokens_out).toLocaleString()} icon={<Coins />} tone="info" hint={`${run.tokens_in.toLocaleString()} in · ${run.tokens_out.toLocaleString()} out`} />
        <StatTile label="Guard flags" value={(run.guard_flags as unknown[]).length} icon={<ShieldAlert />} tone="warning" hint="Input and output checks" />
        <StatTile label="Duration" value={seconds === null ? '—' : `${seconds.toFixed(1)} s`} icon={<Clock />} tone="muted" hint={`graph ${run.graph_version}`} />
      </div>
      <Panel title="Path through the graph" action={<GraphLegend />} className="mb-6">
        <AgentGraph visitedNodes={steps.map((s) => s.node)} status={run.status} height={420} />
      </Panel>
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
        <div className="space-y-6">
          <Panel title="Steps">
            {steps.length === 0 ? <EmptyState>{active ? 'Starting…' : 'No steps recorded.'}</EmptyState> : (
              <Timeline items={steps.map((s) => ({
                id: String(s.sequence), title: NODE_LABELS[s.node] ?? s.node.replaceAll('_', ' '), time: new Date(s.created_at).toLocaleTimeString(),
                tone: s.node === 'human_review' || s.node === 'open_review' ? 'warning' : s.node.includes('guard') || s.node === 'output_checks' ? 'success' : 'primary',
                icon: <Bot />,
              }))} />
            )}
          </Panel>
          <Panel title="Versions">
            <KeyValue items={[
              ['Run id', <span key="id" className="flex items-center gap-1 font-mono text-xs">{run.id}<CopyButton value={run.id} label="Copy run id" /></span>],
              ['Model', <span key="m" className="font-mono text-xs">{run.model_name}</span>],
              ['Graph', run.graph_version],
              ...Object.values(run.prompt_versions as Record<string, string>).map((v) => ['Prompt', <span key={v} className="font-mono text-xs">{v}</span>] as [string, ReactNode]),
            ]} />
          </Panel>
        </div>
        <Panel title={`Tool calls (${calls.length})`} description="Each call was checked against the requester's role before it ran.">
          {calls.length === 0 ? <EmptyState>No tool calls yet.</EmptyState> : (
            <ul className="space-y-2">
              {calls.map((c) => (
                <li key={c.id} className="rounded-xl border bg-muted/40 p-3">
                  <div className="flex items-center gap-2">
                    <Wrench className="size-4 text-muted-foreground" />
                    <code className="flex-1 truncate font-mono text-[13px] font-medium">{c.tool}</code>
                    <span className="rounded-md bg-muted px-1.5 py-0.5 text-xs capitalize">{c.agent.replaceAll('_', ' ')}</span>
                    <StatusBadge value={c.status === 'ok' ? 'completed' : c.status === 'denied' ? 'denied' : 'failed'} />
                    <span className="tabular text-xs text-muted-foreground">{c.duration_ms} ms</span>
                  </div>
                  {(c.policy_reason || c.error) && <p className="mt-1.5 text-[13px] text-destructive">{c.policy_reason || c.error}</p>}
                  {Object.keys(c.result_summary ?? {}).length > 0 && <p className="mt-1.5 truncate font-mono text-xs text-muted-foreground">→ {JSON.stringify(c.result_summary)}</p>}
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  )
}
