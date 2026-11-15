import { type FormEvent, Fragment, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { AnimatePresence, motion } from 'motion/react'
import { ArrowUp, BarChart3, Bot, Gavel, MessageSquarePlus, RotateCcw, Search, Sparkles, UserRound, Wrench } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Textarea } from '@/components/ui/textarea'
import { CopyButton } from '@/components/app/dialogs'
import { Eyebrow } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import { NODE_LABELS } from '@/components/app/run-progress'
import { ErrorAlert } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import {
  useApiV1AssistantMessagesCreate, useApiV1AssistantThreadsList, useApiV1AssistantThreadsRunsList,
} from '@/shared/api/generated/assistant/assistant'
import type { AgentRun } from '@/shared/api/generated/model'
import { useMe } from '@/shared/hooks/useMe'
import { useRunEvents } from '@/shared/hooks/useRunEvents'
import { relativeTime } from '@/shared/ui/common'

const CITE = /\[(candidate|report|policy):([^\]]+)\]/g
const STARTERS = [
  { icon: <Search />, text: 'Who knows FastAPI and LangGraph?' },
  { icon: <BarChart3 />, text: 'How many applications are at each stage?' },
  { icon: <Gavel />, text: 'What is our policy on offer approvals?' },
]
type Source = { kind: 'candidate' | 'report' | 'policy'; ref: string }

function parse(text: string): { parts: (string | number)[]; sources: Source[] } {
  const sources: Source[] = []
  const parts: (string | number)[] = []
  let last = 0
  for (const m of text.matchAll(CITE)) {
    parts.push(text.slice(last, m.index))
    let n = sources.findIndex((s) => s.kind === m[1] && s.ref === m[2])
    if (n < 0) { sources.push({ kind: m[1] as Source['kind'], ref: m[2] }); n = sources.length - 1 }
    parts.push(n + 1)
    last = (m.index ?? 0) + m[0].length
  }
  parts.push(text.slice(last))
  return { parts, sources }
}

function Thinking() {
  return (
    <div className="flex items-center gap-2 py-1 text-sm text-muted-foreground" role="status">
      <span className="flex gap-1">{[0, 1, 2].map((i) => (
        <motion.span key={i} className="size-1.5 rounded-full bg-primary" animate={{ opacity: [0.3, 1, 0.3], y: [0, -3, 0] }} transition={{ duration: 1, repeat: Infinity, delay: i * 0.15 }} />
      ))}</span>
      Searching what you're allowed to see…
    </div>
  )
}

function Turn({ run, me, onRegenerate, onSelect, selected }: { run: AgentRun; me: string; onRegenerate: (q: string) => void; onSelect: () => void; selected: boolean }) {
  const { run: live } = useRunEvents(run.status === 'completed' || run.status === 'failed' ? null : run.id)
  const current = live ?? run
  const question = String((current.input as { message?: string }).message ?? '')
  const answer = String((current.output as { result?: { answer?: string } }).result?.answer ?? '')
  const { parts, sources } = parse(answer)
  return (
    <motion.div initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} className="space-y-4">
      <div className="flex justify-end gap-3">
        <div className="max-w-[78%] rounded-xl rounded-br-md bg-ink px-4 py-2.5 text-[15px] text-background">{question}</div>
        <PersonAvatar name={me} size={30} />
      </div>
      <div className="flex gap-3">
        <span className="grid size-[30px] shrink-0 place-items-center rounded-full bg-brand text-white"><Sparkles className="size-4" /></span>
        <div onClick={onSelect}
          className={cn('min-w-0 max-w-[85%] cursor-pointer glass rounded-xl rounded-bl-md px-4 py-3 transition',
            selected && 'ring-2 ring-primary/30')}>
          {current.status === 'completed' ? (
            <>
              <p className="text-[15px] leading-relaxed whitespace-pre-wrap">
                {parts.map((p, i) => typeof p === 'number'
                  ? <sup key={i} className="mx-0.5 rounded bg-primary/10 px-1 text-xs font-semibold text-violet">{p}</sup>
                  : <Fragment key={i}>{p}</Fragment>)}
              </p>
              {sources.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {sources.map((s, i) => s.kind === 'candidate' ? (
                    <Link key={i} to={`/candidates/${s.ref}`} onClick={(e) => e.stopPropagation()}
                      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium hover:border-primary/40 hover:text-violet">
                      <span className="font-semibold text-violet">{i + 1}</span><UserRound className="size-3" /> Candidate profile
                    </Link>
                  ) : (
                    <span key={i} className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium">
                      <span className="font-semibold text-violet">{i + 1}</span>{s.kind === 'report' ? <BarChart3 className="size-3" /> : <Gavel className="size-3" />}
                      {s.kind} · {s.ref.replaceAll('_', ' ')}
                    </span>
                  ))}
                </div>
              )}
              <div className="mt-2 flex items-center gap-1 border-t pt-2 text-xs text-muted-foreground">
                <span className="flex-1 tabular">{current.tool_call_count} tool call{current.tool_call_count === 1 ? '' : 's'} · {current.tokens_in + current.tokens_out} tokens</span>
                <CopyButton value={answer.replace(CITE, '')} label="Copy answer" />
                <Button variant="ghost" size="icon" className="size-7" aria-label="Ask again" onClick={(e) => { e.stopPropagation(); onRegenerate(question) }}><RotateCcw className="size-3.5" /></Button>
              </div>
            </>
          ) : current.error ? <p className="text-sm text-destructive">{current.error}</p> : <Thinking />}
        </div>
      </div>
    </motion.div>
  )
}

function AgentPanel({ run }: { run: AgentRun | undefined }) {
  const { run: live } = useRunEvents(run?.id)
  const current = live ?? run
  if (!current) {
    return <div className="p-5 text-sm text-muted-foreground">Ask a question to watch the agent work: which tools it calls, what it may see, and where each answer comes from.</div>
  }
  const steps = live && 'steps' in live ? [...live.steps] : []
  const calls = live && 'tool_calls' in live ? [...live.tool_calls] : []
  return (
    <div className="space-y-5 p-5">
      <div className="flex items-center gap-2"><Eyebrow className="flex-1">Agent activity</Eyebrow><StatusBadge value={current.status} /></div>
      <ol className="space-y-2">
        {steps.map((s) => (
          <li key={s.sequence} className="flex items-start gap-2 text-[13px]">
            <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-primary" />{NODE_LABELS[s.node] ?? s.node}
          </li>
        ))}
      </ol>
      <div>
        <Eyebrow className="mb-2">Tool calls</Eyebrow>
        {calls.length === 0 ? <p className="text-[13px] text-muted-foreground">None yet.</p> : (
          <ul className="space-y-1.5">
            {calls.map((c) => (
              <li key={c.id} className="flex items-center gap-2 rounded-lg border bg-background px-2.5 py-1.5">
                <Wrench className="size-3.5 text-muted-foreground" />
                <code className="flex-1 truncate font-mono text-xs">{c.tool}</code>
                <StatusBadge value={c.status === 'ok' ? 'completed' : c.status === 'denied' ? 'denied' : 'failed'} />
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="rounded-xl bg-muted/70 p-3 text-xs text-muted-foreground">Every tool call is checked against your role and logged. Contact details are removed from what the model reads.</p>
      <Button variant="outline" size="sm" asChild className="w-full"><Link to={`/agents/${current.id}`}>Open full run</Link></Button>
    </div>
  )
}

export function AssistantPage() {
  const { me } = useMe()
  const threads = useApiV1AssistantThreadsList()
  const [threadId, setThreadId] = useState<string | null>(null)
  const [selected, setSelected] = useState<string | null>(null)
  const runs = useApiV1AssistantThreadsRunsList(threadId ?? '', { query: { enabled: Boolean(threadId), refetchInterval: 4000 } })
  const send = useApiV1AssistantMessagesCreate()
  const [message, setMessage] = useState('')
  const bottom = useRef<HTMLDivElement>(null)
  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }) }, [runs.data?.length, runs.data?.at(-1)?.status])

  const ask = (text: string) => {
    if (!text.trim() || send.isPending) return
    send.mutate({ data: { message: text, thread_id: threadId } }, {
      onSuccess: (run) => { setThreadId(run.thread_id ?? null); setSelected(run.id); setMessage('') },
    })
  }
  const submit = (e: FormEvent) => { e.preventDefault(); ask(message) }
  const list = runs.data ?? []
  const focusRun = list.find((r) => r.id === selected) ?? list.at(-1)

  return (
    <div className="-mx-4 -my-6 grid h-[calc(100svh-4rem)] grid-cols-1 md:-mx-8 md:-my-8 lg:grid-cols-[250px_minmax(0,1fr)] xl:grid-cols-[250px_minmax(0,1fr)_320px]">
      <aside className="hidden flex-col border-r bg-card/60 lg:flex">
        <div className="p-4">
          <Button className="w-full" variant="outline" onClick={() => { setThreadId(null); setSelected(null) }}><MessageSquarePlus /> New conversation</Button>
        </div>
        <Eyebrow className="px-5 pb-2">Recent</Eyebrow>
        <ScrollArea className="flex-1 px-2">
          {(threads.data?.results ?? []).length === 0 && <p className="px-3 text-sm text-muted-foreground">No conversations yet.</p>}
          {threads.data?.results?.map((t) => (
            <button key={t.id} type="button" onClick={() => { setThreadId(t.id); setSelected(null) }}
              className={cn('mb-0.5 w-full rounded-lg px-3 py-2 text-left hover:bg-muted', t.id === threadId && 'bg-accent text-accent-foreground')}>
              <span className="block truncate text-sm font-medium">{t.title || 'Conversation'}</span>
              <span className="block text-xs text-muted-foreground">{relativeTime(t.updated_at)}</span>
            </button>
          ))}
        </ScrollArea>
      </aside>

      <section className="flex min-h-0 flex-col">
        <ScrollArea className="min-h-0 flex-1">
          <div className="mx-auto max-w-3xl space-y-8 px-4 py-8 md:px-8">
            <AnimatePresence>
              {!threadId && (
                <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="pt-10 text-center">
                  <span className="mx-auto grid size-14 place-items-center rounded-xl bg-brand text-white"><Bot className="size-7" /></span>
                  <h1 className="mt-5 text-2xl font-semibold">Ask your AI recruiter</h1>
                  <p className="mx-auto mt-2 max-w-md text-muted-foreground">It searches candidates, pipeline numbers and hiring policy, but only what you are allowed to see. It cannot change records or send anything.</p>
                  <div className="mx-auto mt-8 grid max-w-2xl gap-3 sm:grid-cols-3">
                    {STARTERS.map((s) => (
                      <button key={s.text} type="button" onClick={() => ask(s.text)} aria-label={s.text}
                        className="group glass rounded-xl p-4 text-left text-sm transition hover:-translate-y-0.5 hover:border-primary/30 hover:shadow-md">
                        <span className="mb-3 grid size-8 place-items-center rounded-lg bg-primary/15 text-violet [&_svg]:size-4">{s.icon}</span>{s.text}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
            {list.map((run) => (
              <Turn key={run.id} run={run} me={me?.full_name ?? 'You'} onRegenerate={ask} selected={focusRun?.id === run.id} onSelect={() => setSelected(run.id)} />
            ))}
            <div ref={bottom} />
          </div>
        </ScrollArea>
        <div className="border-t bg-background/80 px-4 py-4 backdrop-blur md:px-8">
          <ErrorAlert error={send.error} />
          <form onSubmit={submit} className="mx-auto flex max-w-3xl items-end gap-2 glass rounded-xl p-2 focus-within:ring-2 focus-within:ring-primary/25">
            <Textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={1} aria-label="Message"
              onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(message) } }}
              placeholder="Ask about candidates, numbers or policy…" className="max-h-40 min-h-10 resize-none border-0 bg-transparent shadow-none focus-visible:ring-0" />
            <Button type="submit" size="icon" className="shrink-0 rounded-xl" disabled={!message.trim() || send.isPending} aria-label="Send"><ArrowUp /></Button>
          </form>
          <p className="mx-auto mt-2 max-w-3xl text-center text-xs text-muted-foreground">Answers cite their sources. Enter to send · Shift+Enter for a new line.</p>
        </div>
      </section>

      <aside className="hidden border-l bg-card/60 xl:block"><ScrollArea className="h-full"><AgentPanel run={focusRun} /></ScrollArea></aside>
    </div>
  )
}
