import { memo, useMemo } from 'react'
import { useTheme } from 'next-themes'
import { Background, Controls, Handle, MarkerType, Position, ReactFlow, type Edge, type Node, type NodeProps } from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Bot, CircleDot, Flag, Hourglass, ShieldCheck, Split, UserCheck } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Skeleton } from '@/components/ui/skeleton'
import { useApiV1AgentGraphRetrieve } from '@/shared/api/generated/agent-runs/agent-runs'

type State = 'idle' | 'visited' | 'current' | 'waiting'
type GraphNodeData = { label: string; group: string; state: State }

const GROUP_STYLE: Record<string, string> = {
  agent: 'border-primary/30', guard: 'border-success/40', human: 'border-warning/50', control: 'border-border', terminal: 'border-border',
}
const ICONS: Record<string, React.ReactNode> = {
  agent: <Bot />, guard: <ShieldCheck />, human: <UserCheck />, control: <Split />, terminal: <Flag />,
}
const PRETTY: Record<string, string> = {
  __start__: 'start', __end__: 'end', guard_input: 'input guard', output_checks: 'output guard', open_review: 'open approval',
  human_review: 'human review', apply_decision: 'apply decision', job_jd: 'JD generation', comms: 'communication',
  candidates: 'matching', match_prepare: 'gather evidence', assess_application: 'assess (parallel)', match_save: 'save matrices',
}

const GraphNode = memo(function GraphNode({ data }: NodeProps<Node<GraphNodeData>>) {
  const { label, group, state } = data
  return (
    <div className={cn('flex items-center gap-2 rounded-xl border-2 bg-popover px-3 py-1.5 text-[13px] font-medium shadow-sm transition-all',
      GROUP_STYLE[group], state === 'idle' && 'opacity-55',
      state === 'visited' && 'border-primary bg-primary/8',
      state === 'current' && 'border-primary bg-primary text-primary-foreground shadow-lg shadow-primary/30',
      state === 'waiting' && 'animate-pulse border-warning bg-warning/15 shadow-lg shadow-warning/30')}>
      <Handle type="target" position={Position.Left} className="!size-1.5 !border-0 !bg-border" />
      <span className="[&_svg]:size-3.5">{state === 'waiting' ? <Hourglass /> : ICONS[group] ?? <CircleDot />}</span>
      <span className="whitespace-nowrap capitalize">{PRETTY[label] ?? label.replaceAll('_', ' ')}</span>
      <Handle type="source" position={Position.Right} className="!size-1.5 !border-0 !bg-border" />
    </div>
  )
})

const COLUMN: Record<string, number> = { __start__: 0, guard_input: 1, supervisor: 2, output_checks: 4, open_review: 5, human_review: 6, apply_decision: 7, audit: 8, __end__: 9 }

/**
 * The supervisor graph as LangGraph built it. With a run's steps, the path it took is lit,
 * the last step is marked, and a run waiting for a person pulses on human review.
 */
export function AgentGraph({ visitedNodes = [], status, height = 520 }: { visitedNodes?: string[]; status?: string; height?: number }) {
  const graph = useApiV1AgentGraphRetrieve({ query: { staleTime: Infinity } })
  const { resolvedTheme } = useTheme()
  const { nodes, edges } = useMemo(() => {
    if (!graph.data) return { nodes: [], edges: [] }
    const visited = new Set(visitedNodes.flatMap((n) => n === 'candidates' ? ['candidates:match_prepare', 'candidates:assess_application', 'candidates:match_save'] : [n]))
    if (visitedNodes.length) visited.add('__start__')
    if (status === 'completed') visited.add('__end__')
    const last = visitedNodes.at(-1)
    const agents = graph.data.nodes.filter((n) => !(n.id in COLUMN))
    const rowOf = new Map(agents.map((n, i) => [n.id, i]))
    const mid = (agents.length - 1) / 2
    const nodes: Node<GraphNodeData>[] = graph.data.nodes.map((n) => {
      const col = COLUMN[n.id] ?? 3
      const row = rowOf.has(n.id) ? (rowOf.get(n.id) as number) - mid : 0
      const state: State = status === 'awaiting_review' && n.id === 'human_review' ? 'waiting'
        : n.id === last && (status === 'running' || status === 'queued') ? 'current' : visited.has(n.id) ? 'visited' : 'idle'
      return { id: n.id, type: 'graph', position: { x: col * 150 + (col > 3 ? 60 : 0), y: row * 44 }, data: { label: n.label, group: n.group, state }, draggable: false }
    })
    const edges: Edge[] = graph.data.edges.map((e, i) => {
      const lit = visited.has(e.source) && visited.has(e.target)
      const back = e.source === 'apply_decision' && e.target !== 'audit'
      return {
        id: `${e.source}-${e.target}-${i}`, source: e.source, target: e.target, animated: lit,
        style: { stroke: lit ? 'var(--primary)' : 'var(--border)', strokeWidth: lit ? 2 : 1, strokeDasharray: e.conditional && !lit ? '4 4' : undefined, opacity: back && !lit ? 0.25 : 1 },
        markerEnd: { type: MarkerType.ArrowClosed, color: lit ? 'var(--primary)' : 'var(--border)', width: 14, height: 14 },
      }
    })
    return { nodes, edges }
  }, [graph.data, visitedNodes, status])

  if (!graph.data) return <Skeleton className="w-full rounded-xl" style={{ height }} />
  return (
    <div className="overflow-hidden rounded-xl border bg-[radial-gradient(var(--border)_1px,transparent_1px)] [background-size:18px_18px]" style={{ height }}>
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={{ graph: GraphNode }} fitView fitViewOptions={{ padding: 0.06 }}
        colorMode={resolvedTheme === 'dark' ? 'dark' : 'light'} proOptions={{ hideAttribution: true }}
        nodesConnectable={false} elementsSelectable={false} minZoom={0.3} maxZoom={1.6}>
        <Background gap={18} size={0} />
        <Controls showInteractive={false} position="bottom-right" />
      </ReactFlow>
    </div>
  )
}

export function GraphLegend() {
  const items: [string, string][] = [['Agent', 'border-primary/40'], ['Guard', 'border-success/50'], ['Needs a person', 'border-warning/60'], ['Path taken', 'border-primary bg-primary/10']]
  return (
    <div className="flex flex-wrap gap-3 text-xs text-muted-foreground">
      {items.map(([label, cls]) => <span key={label} className="flex items-center gap-1.5"><span className={cn('size-3 rounded border-2', cls)} />{label}</span>)}
    </div>
  )
}
