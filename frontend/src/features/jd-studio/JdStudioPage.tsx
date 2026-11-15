import { Fragment, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { toast } from 'sonner'
import { ArrowLeft, CheckCircle2, FileText, History, Save, ShieldAlert, Sparkles } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { PageHeader, Panel } from '@/components/app/page'
import { RunProgress } from '@/components/app/run-progress'
import { EmptyState, ErrorAlert } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { useApiV1ApprovalsList } from '@/shared/api/generated/approvals/approvals'
import { useApiV1JobDescriptionsList, useApiV1JobDescriptionsPartialUpdate } from '@/shared/api/generated/jobs/jobs'
import type { JobDescription } from '@/shared/api/generated/model'
import { useApiV1RequisitionsJdDraftsCreate, useApiV1RequisitionsRetrieve } from '@/shared/api/generated/requisitions/requisitions'
import { shortDate } from '@/shared/ui/common'

type Requirement = { name: string; level: string }
type Flag = { term: string; category: string; suggestion: string }

export function LanguageFlags({ flags }: { flags: Flag[] }) {
  if (!flags.length) {
    return <p className="flex items-center gap-2 rounded-xl bg-success/10 px-3.5 py-2.5 text-sm text-success ring-1 ring-success/25 ring-inset"><CheckCircle2 className="size-4" /> No biased or exclusionary wording found.</p>
  }
  return (
    <div className="rounded-xl bg-warning/10 px-4 py-3 ring-1 ring-warning/30 ring-inset">
      <p className="flex items-center gap-2 text-sm font-semibold text-warning"><ShieldAlert className="size-4" /> Language to review ({flags.length})</p>
      <ul className="mt-2 space-y-1.5 text-[13px]">
        {flags.map((f, i) => (
          <li key={i}><mark className="hl bg-transparent font-semibold">{f.term}</mark> <span className="text-muted-foreground">({f.category.replaceAll('_', ' ')})</span> → {f.suggestion}</li>
        ))}
      </ul>
    </div>
  )
}

const LEVEL_STYLE: Record<string, string> = {
  mandatory: 'bg-pink/12 text-pink ring-pink/30', required: 'bg-primary/15 text-violet ring-primary/30', preferred: 'bg-muted text-foreground/80 ring-border',
}

export function RequirementChips({ requirements }: { requirements: Requirement[] }) {
  if (!requirements.length) return null
  return (
    <div className="flex flex-wrap gap-1.5">
      {requirements.map((r) => (
        <span key={r.name} className={cn('inline-flex items-center gap-1.5 rounded-lg px-2 py-0.5 text-xs font-medium ring-1 ring-inset', LEVEL_STYLE[r.level] ?? LEVEL_STYLE.preferred)}>
          {r.name}<span className="text-xs tracking-wide uppercase opacity-70">{r.level}</span>
        </span>
      ))}
    </div>
  )
}

/** A small Markdown reader for JDs: headings, bullets and paragraphs. */
export function JdPreview({ body }: { body: string }) {
  const blocks: ReactNode[] = []
  let bullets: string[] = []
  const flush = (key: number) => { if (bullets.length) { blocks.push(<ul key={`u${key}`} className="my-2 list-disc space-y-1 pl-5 marker:text-violet">{bullets.map((b, i) => <li key={i}>{b}</li>)}</ul>); bullets = [] } }
  body.split('\n').forEach((raw, i) => {
    const line = raw.trim()
    if (/^[-*] /.test(line)) { bullets.push(line.slice(2)); return }
    flush(i)
    if (!line) return
    if (line.startsWith('### ')) blocks.push(<h4 key={i} className="mt-4 mb-1 text-[15px] font-semibold">{line.slice(4)}</h4>)
    else if (line.startsWith('## ')) blocks.push(<h3 key={i} className="mt-5 mb-1.5 text-lg font-semibold">{line.slice(3)}</h3>)
    else if (line.startsWith('# ')) blocks.push(<h2 key={i} className="text-brand mb-2 w-fit text-2xl font-semibold">{line.slice(2)}</h2>)
    else blocks.push(<p key={i} className="my-2">{line.replaceAll('**', '')}</p>)
  })
  flush(-1)
  return <article className="text-[15px] leading-relaxed text-foreground/90">{blocks.map((b, i) => <Fragment key={i}>{b}</Fragment>)}</article>
}

function DraftEditor({ jd }: { jd: JobDescription }) {
  const [body, setBody] = useState(jd.body ?? '')
  const save = useApiV1JobDescriptionsPartialUpdate()
  const editable = jd.status === 'draft'
  return (
    <div className="space-y-4">
      <ErrorAlert error={save.error} />
      <LanguageFlags flags={(jd.compliance_flags ?? []) as Flag[]} />
      <RequirementChips requirements={(jd.requirements ?? []) as Requirement[]} />
      <Tabs defaultValue="preview">
        <div className="flex items-center gap-2">
          <TabsList><TabsTrigger value="preview">Preview</TabsTrigger><TabsTrigger value="edit">{editable ? 'Edit' : 'Markdown'}</TabsTrigger></TabsList>
          <span className="flex-1" />
          {editable && <Button size="sm" variant="outline" disabled={save.isPending || body === jd.body}
            onClick={() => save.mutate({ id: jd.id, data: { body } }, { onSuccess: () => toast.success('Draft saved') })}><Save /> Save draft</Button>}
        </div>
        <TabsContent value="preview" className="mt-3 rounded-xl border bg-muted/30 p-6"><JdPreview body={body} /></TabsContent>
        <TabsContent value="edit" className="mt-3">
          <Textarea value={body} onChange={(e) => setBody(e.target.value)} rows={20} disabled={!editable} className="font-mono text-[13px] leading-relaxed" aria-label="JD markdown" />
        </TabsContent>
      </Tabs>
    </div>
  )
}

export function JdStudioPage() {
  const { id = '' } = useParams()
  const requisition = useApiV1RequisitionsRetrieve(id)
  const jds = useApiV1JobDescriptionsList({ requisition: id })
  const approvals = useApiV1ApprovalsList({ requisition: id, kind: 'job_description', status: 'pending' })
  const generate = useApiV1RequisitionsJdDraftsCreate()
  const [selected, setSelected] = useState<string | null>(null)
  const list = jds.data?.results ?? []
  const current = list.find((jd) => jd.id === selected) ?? list[0]
  const pending = approvals.data?.results?.find((a) => a.target_id === current?.id)

  return (
    <>
      <PageHeader title="JD studio" crumbs={[{ label: 'Jobs', to: '/requisitions' }, { label: requisition.data?.title ?? 'Job', to: `/requisitions/${id}` }, { label: 'JD studio' }]}
        description="The JD agent drafts from the job and your templates, and flags biased wording. A recruiter edits and approves."
        actions={<>
          <Button variant="outline" asChild><Link to={`/requisitions/${id}`}><ArrowLeft /> Back to job</Link></Button>
          <Button disabled={generate.isPending} onClick={() => generate.mutate({ id, data: {} })}><Sparkles /> Draft a JD</Button>
        </>} />
      <ErrorAlert error={generate.error} />
      {generate.data && <div className="mb-6"><RunProgress runId={generate.data.id} title="JD generation agent" /></div>}
      <div className="grid grid-cols-1 items-start gap-6 lg:grid-cols-[280px_minmax(0,1fr)]">
        <Panel title="Versions" icon={<History />} bodyClassName="px-2 pb-2">
          {list.length === 0 ? <p className="px-3 pb-3 text-sm text-muted-foreground">No drafts yet.</p> : (
            <ul className="space-y-1">
              {list.map((jd) => (
                <li key={jd.id}>
                  <button type="button" onClick={() => setSelected(jd.id)}
                    className={cn('flex w-full items-start gap-3 rounded-xl px-3 py-2.5 text-left transition hover:bg-accent', jd.id === current?.id && 'bg-brand-soft ring-1 ring-violet/35 ring-inset')}>
                    <span className="font-heading mt-0.5 text-sm font-bold text-violet">v{jd.version}</span>
                    <span className="min-w-0 flex-1"><span className="block truncate text-sm font-medium">{jd.title}</span>
                      <span className="block text-xs text-muted-foreground">{shortDate(jd.created_at)}</span></span>
                    <StatusBadge value={jd.status} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Panel>
        {current ? (
          <Panel icon={<FileText />} title={<>v{current.version} · {current.title}</>} description={current.prompt_version ? `Prompt ${current.prompt_version}` : undefined}
            action={<div className="flex items-center gap-2"><StatusBadge value={current.status} />
              {pending && <Button size="sm" asChild><Link to={`/approvals/${pending.id}`}>Review and approve</Link></Button>}</div>}>
            <DraftEditor key={current.id} jd={current} />
          </Panel>
        ) : (
          <Panel><EmptyState icon={<Sparkles />} title="No JD yet" action={<Button onClick={() => generate.mutate({ id, data: {} })}><Sparkles /> Draft a JD</Button>}>
            The agent writes a first draft from the job's summary and skills. You edit it before anyone sees it.</EmptyState></Panel>
        )}
      </div>
    </>
  )
}
