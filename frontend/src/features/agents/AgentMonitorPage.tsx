import { useNavigate } from 'react-router'
import { AlertOctagon, Bot, Coins, Hourglass } from 'lucide-react'
import { DataTable } from '@/components/app/data-table'
import { PageHeader, Panel } from '@/components/app/page'
import { StatTile } from '@/components/app/stat'
import { EmptyState, ErrorAlert } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { useApiV1AgentRunsList } from '@/shared/api/generated/agent-runs/agent-runs'
import type { AgentRun } from '@/shared/api/generated/model'
import { relativeTime } from '@/shared/ui/common'
import { AgentGraph, GraphLegend } from './AgentGraph'

export function AgentMonitorPage() {
  const navigate = useNavigate()
  const runs = useApiV1AgentRunsList(undefined, { query: { refetchInterval: 8000 } })
  const all = runs.data?.results ?? []
  const tokens = all.reduce((sum, r) => sum + r.tokens_in + r.tokens_out, 0)

  return (
    <>
      <PageHeader crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Agent monitor' }]} title="Agent monitor"
        description="How each run moves through the supervisor graph, which tools it called, and where it waits for a person." />
      <div className="mb-6 grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatTile label="Runs (latest page)" value={all.length} icon={<Bot />} loading={runs.isLoading} />
        <StatTile label="Waiting for a person" value={all.filter((r) => r.status === 'awaiting_review').length} icon={<Hourglass />} tone="warning" loading={runs.isLoading} to="/approvals" />
        <StatTile label="Failed or over budget" value={all.filter((r) => r.status === 'failed' || r.status === 'budget_exceeded').length} icon={<AlertOctagon />} tone="destructive" loading={runs.isLoading} />
        <StatTile label="Tokens used" value={tokens.toLocaleString()} icon={<Coins />} tone="info" loading={runs.isLoading} hint="Across these runs" />
      </div>
      <Panel title="Supervisor graph" description="Guards check input and output; agents only draft; anything that affects a candidate stops at human review." action={<GraphLegend />} className="mb-6">
        <AgentGraph height={560} />
      </Panel>
      <ErrorAlert error={runs.error} />
      <Panel flush title="Runs" className="overflow-hidden">
        <DataTable rows={all} rowKey={(r) => r.id} loading={runs.isLoading} onOpen={(r) => navigate(`/agents/${r.id}`)}
          filterText={(r) => `${r.kind} ${r.status} ${r.model_name}`} filterPlaceholder="Filter runs" initialSort={{ key: 'when', desc: true }}
          exportName="agent-runs"
          facets={[{ key: 'kind', label: 'Agent', value: (r) => r.kind }, { key: 'status', label: 'Status', value: (r) => r.status }, { key: 'model', label: 'Model', value: (r) => r.model_name, format: (v) => v }]}
          empty={<EmptyState icon={<Bot />} title="No runs here">Runs appear when you draft a JD, run matching, or ask the AI recruiter.</EmptyState>}
          columns={[
            { key: 'kind', header: 'Agent', sort: (r: AgentRun) => r.kind, cell: (r: AgentRun) => (
              <div className="flex items-center gap-3">
                <span className="bg-brand-soft grid size-9 place-items-center rounded-xl text-violet ring-1 ring-violet/30 ring-inset"><Bot className="size-4" /></span>
                <span><span className="block font-semibold capitalize">{r.kind.replaceAll('_', ' ')}</span><span className="font-mono text-xs text-muted-foreground">{r.id.slice(0, 8)}</span></span>
              </div>) },
            { key: 'status', header: 'Status', sort: (r: AgentRun) => r.status, cell: (r: AgentRun) => <StatusBadge value={r.status} /> },
            { key: 'tools', header: 'Tool calls', hide: 'md', sort: (r: AgentRun) => r.tool_call_count, cell: (r: AgentRun) => <span className="tabular">{r.tool_call_count}</span> },
            { key: 'tokens', header: 'Tokens', hide: 'md', sort: (r: AgentRun) => r.tokens_in + r.tokens_out, cell: (r: AgentRun) => <span className="tabular">{(r.tokens_in + r.tokens_out).toLocaleString()}</span> },
            { key: 'model', header: 'Model', hide: 'lg', cell: (r: AgentRun) => <span className="font-mono text-xs">{r.model_name}</span> },
            { key: 'when', header: 'Started', sort: (r: AgentRun) => r.created_at, cell: (r: AgentRun) => <span className="text-muted-foreground">{relativeTime(r.created_at)}</span> },
          ]} />
      </Panel>
    </>
  )
}
