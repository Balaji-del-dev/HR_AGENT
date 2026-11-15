import { useState, type ReactNode } from 'react'
import { useTheme } from 'next-themes'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Activity, BarChart3, ChevronDown, Clock, Filter, Scale, Users } from 'lucide-react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { PageHeader, Panel } from '@/components/app/page'
import { StatTile } from '@/components/app/stat'
import { ErrorAlert, PageSkeleton } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { useApiV1AnalyticsPipelineRetrieve } from '@/shared/api/generated/analytics/analytics'
import type { ApiV1AnalyticsPipelineRetrieveReport, ReportOut } from '@/shared/api/generated/model'
import { useApiV1RequisitionsList } from '@/shared/api/generated/requisitions/requisitions'

// Categorical pair validated per mode with the dataviz validator: slot 1 violet, slot 2 cyan.
const PALETTES = {
  dark: { series: ['#7c7af0', '#15a394'], ink: { primary: '#e9eaf7', secondary: '#c3c6e0', muted: '#969bbf', grid: 'rgba(255,255,255,0.07)', axis: 'rgba(255,255,255,0.14)' }, cursor: 'rgba(255,255,255,0.05)', surface: '#1b1f2a' },
  light: { series: ['#5e5be8', '#0e9384'], ink: { primary: '#14152b', secondary: '#3d405e', muted: '#5d6080', grid: 'rgba(20,21,43,0.08)', axis: 'rgba(20,21,43,0.16)' }, cursor: 'rgba(20,21,43,0.04)', surface: '#ffffff' },
}

function useReport(report: ApiV1AnalyticsPipelineRetrieveReport, requisition: string) {
  return useApiV1AnalyticsPipelineRetrieve({ report, ...(requisition ? { requisition } : {}) })
}

function rowsToObjects(report: ReportOut | undefined): Record<string, string | number>[] {
  if (!report) return []
  return report.rows.map((row) => Object.fromEntries(report.columns.map((c, i) => [c, row[i] as string | number])))
}

function ReportTable({ report }: { report: ReportOut }) {
  return (
    <div className="overflow-hidden rounded-xl border">
      <Table>
        <TableHeader className="bg-muted/50"><TableRow className="hover:bg-transparent">{report.columns.map((c) => <TableHead key={c} className="text-xs tracking-wider text-muted-foreground uppercase">{c.replaceAll('_', ' ')}</TableHead>)}</TableRow></TableHeader>
        <TableBody>{report.rows.map((row, i) => <TableRow key={i}>{row.map((v, j) => <TableCell key={j} className="tabular capitalize">{String(v).replaceAll('_', ' ')}</TableCell>)}</TableRow>)}</TableBody>
      </Table>
    </div>
  )
}

/** Every chart has its table one click away and shows the read-only query it ran. */
function ChartCard({ title, description, report, icon, children }: { title: string; description?: string; report?: ReportOut; icon: ReactNode; children: ReactNode }) {
  return (
    <Panel title={title} description={description} icon={icon}>
      <div className="h-[280px]">{children}</div>
      {report && (
        <details className="group mt-3 rounded-xl border bg-muted/30">
          <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-sm text-muted-foreground hover:text-foreground">
            <ChevronDown className="size-4 transition group-open:rotate-180" /> Table and query
          </summary>
          <div className="space-y-3 px-3 pb-3">
            <ReportTable report={report} />
            <pre className="overflow-x-auto rounded-lg bg-muted p-3 font-mono text-xs leading-relaxed whitespace-pre-wrap text-muted-foreground">{report.query}</pre>
            {report.notes.map((n) => <p key={n} className="text-xs text-muted-foreground">{n}</p>)}
          </div>
        </details>
      )}
    </Panel>
  )
}

export function AnalyticsPage() {
  const { resolvedTheme } = useTheme()
  const scheme = PALETTES[resolvedTheme === 'light' ? 'light' : 'dark']
  const [SERIES, INK] = [scheme.series, scheme.ink]
  const axisProps = { stroke: INK.axis, tick: { fill: INK.muted, fontSize: 12 }, tickLine: false }
  const tooltipProps = {
    cursor: { fill: scheme.cursor }, itemStyle: { color: INK.primary, fontSize: 13 }, labelStyle: { color: INK.primary, fontWeight: 600, textTransform: 'capitalize' as const },
    contentStyle: { background: scheme.surface, border: `1px solid ${INK.axis}`, borderRadius: 12, boxShadow: '0 12px 30px -10px rgba(0,0,0,0.5)' },
  }
  const [requisition, setRequisition] = useState('all')
  const req = requisition === 'all' ? '' : requisition
  const requisitions = useApiV1RequisitionsList()
  const funnel = useReport('pipeline_funnel', req)
  const sources = useReport('source_breakdown', req)
  const time = useReport('time_in_stage', req)
  const override = useReport('override_rate', req)
  const health = useReport('agent_health', req)
  const overrideRow = override.data?.rows[0] as number[] | undefined
  const funnelRows = rowsToObjects(funnel.data)
  const total = funnelRows.reduce((n, r) => n + Number(r.applications ?? 0), 0)
  const hired = Number(funnelRows.find((r) => r.stage === 'hired')?.applications ?? 0)
  const timeRows = rowsToObjects(time.data)
  const slowest = [...timeRows].filter((r) => Number(r.avg_hours) > 0).sort((a, b) => Number(b.avg_hours) - Number(a.avg_hours))[0]

  return (
    <>
      <PageHeader title="Recruitment analytics" crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Analytics' }]}
        description="Read-only reports over the jobs you can see. Each chart shows its table and the query behind it."
        actions={
          <div className="flex items-center gap-2">
            <Filter className="size-4 text-muted-foreground" />
            <Select value={requisition} onValueChange={setRequisition}>
              <SelectTrigger className="w-64" aria-label="Job"><SelectValue /></SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All jobs</SelectItem>
                {requisitions.data?.results?.map((r) => <SelectItem key={r.id} value={r.id}>{r.title}</SelectItem>)}
              </SelectContent>
            </Select>
          </div>
        } />
      <ErrorAlert error={funnel.error} />
      {funnel.isLoading ? <PageSkeleton /> : (
        <div className="space-y-6">
          <section className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <StatTile label="Applications" value={total} icon={<Users />} tone="primary" hint="Across every stage" />
            <StatTile label="Hired" value={hired} icon={<Activity />} tone="success" hint={total ? `${((hired / total) * 100).toFixed(1)}% of applications` : 'No applications yet'} />
            <StatTile label="Slowest stage" value={slowest ? <span className="capitalize">{String(slowest.stage)}</span> : '—'} icon={<Clock />} tone="warning"
              hint={slowest ? `${Number(slowest.avg_hours).toFixed(1)} h on average` : 'No stage moves yet'} />
            <StatTile label="Against the evidence" value={overrideRow ? `${overrideRow[2]}%` : '—'} icon={<Scale />} tone="pink"
              hint={overrideRow ? `${overrideRow[1]} of ${overrideRow[0]} decisions` : 'No decisions yet'} />
          </section>
          <p className="-mt-2 text-xs text-muted-foreground">A decision against the evidence is a review signal, not an error: people may know more than the resume says.</p>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <ChartCard title="Applications by stage" description="How far applications have moved" report={funnel.data} icon={<BarChart3 />}>
              <ResponsiveContainer>
                <BarChart data={funnelRows} margin={{ top: 8, right: 8, bottom: 0, left: -16 }}>
                  <CartesianGrid vertical={false} stroke={INK.grid} />
                  <XAxis dataKey="stage" {...axisProps} interval={0} angle={-30} textAnchor="end" height={56} tickFormatter={(v: string) => v[0]?.toUpperCase() + v.slice(1)} />
                  <YAxis allowDecimals={false} {...axisProps} axisLine={false} />
                  <Tooltip {...tooltipProps} />
                  <Bar dataKey="applications" name="Applications" fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={40} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
            <ChartCard title="Applications and hires by source" description="Where people come from, and where hires come from" report={sources.data} icon={<Users />}>
              <ResponsiveContainer>
                <BarChart data={rowsToObjects(sources.data)} margin={{ top: 8, right: 8, bottom: 0, left: -16 }} barGap={2}>
                  <CartesianGrid vertical={false} stroke={INK.grid} />
                  <XAxis dataKey="source" {...axisProps} interval={0} tickFormatter={(v: string) => v.replaceAll('_', ' ')} />
                  <YAxis allowDecimals={false} {...axisProps} axisLine={false} />
                  <Tooltip {...tooltipProps} />
                  <Legend iconType="circle" wrapperStyle={{ fontSize: 12 }} formatter={(value) => <span style={{ color: INK.secondary }}>{value}</span>} />
                  <Bar dataKey="applications" name="Applications" fill={SERIES[0]} radius={[4, 4, 0, 0]} maxBarSize={30} />
                  <Bar dataKey="hired" name="Hired" fill={SERIES[1]} radius={[4, 4, 0, 0]} maxBarSize={30} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
          </div>

          <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
            <ChartCard title="Average hours in each stage" description="Where candidates wait longest" report={time.data} icon={<Clock />}>
              <ResponsiveContainer>
                <BarChart data={timeRows} layout="vertical" margin={{ top: 8, right: 16, bottom: 0, left: 12 }}>
                  <CartesianGrid horizontal={false} stroke={INK.grid} />
                  <XAxis type="number" {...axisProps} />
                  <YAxis type="category" dataKey="stage" width={92} {...axisProps} axisLine={false} tickFormatter={(v: string) => v[0]?.toUpperCase() + v.slice(1)} />
                  <Tooltip {...tooltipProps} />
                  <Bar dataKey="avg_hours" name="Average hours" fill={SERIES[0]} radius={[0, 4, 4, 0]} maxBarSize={22} />
                </BarChart>
              </ResponsiveContainer>
            </ChartCard>
            <Panel title="Agent runs" description="By agent and outcome" icon={<Activity />}>
              {health.data?.notes.map((n) => <p key={n} className="mb-3 rounded-xl bg-success/10 px-3 py-2 text-[13px] text-success ring-1 ring-success/25 ring-inset">{n} (must stay at zero)</p>)}
              {health.data && (
                <div className="overflow-hidden rounded-xl border">
                  <Table>
                    <TableHeader className="bg-muted/50"><TableRow className="hover:bg-transparent">{health.data.columns.map((c) => <TableHead key={c} className="text-xs tracking-wider text-muted-foreground uppercase">{c.replaceAll('_', ' ')}</TableHead>)}</TableRow></TableHeader>
                    <TableBody>
                      {health.data.rows.map((row, i) => (
                        <TableRow key={i}>
                          {row.map((v, j) => (
                            <TableCell key={j} className="tabular">
                              {health.data?.columns[j] === 'status' ? <StatusBadge value={String(v)} /> : j === 0 ? <span className="font-medium capitalize">{String(v).replaceAll('_', ' ')}</span> : String(v)}
                            </TableCell>
                          ))}
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </div>
              )}
            </Panel>
          </div>
        </div>
      )}
    </>
  )
}
