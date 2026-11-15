import { useSearchParams, Link } from 'react-router'
import { useQueries } from '@tanstack/react-query'
import { CircleHelp } from 'lucide-react'
import { PageHeader, Panel } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import { EmptyState, PageSkeleton } from '@/components/app/states'
import { StatusBadge } from '@/components/app/status'
import { useSession } from '@/app/session'
import {
  getApiV1ApplicationsAssessmentRetrieveQueryOptions, getApiV1ApplicationsListQueryOptions,
} from '@/shared/api/generated/applications/applications'
import { getApiV1CandidatesRetrieveQueryOptions } from '@/shared/api/generated/candidates/candidates'
import type { Assessment, CandidateDetail } from '@/shared/api/generated/model'

type Evidence = { quote: string }

/** Side by side, criterion by criterion. A comparison of evidence, never a ranking. */
export function CandidateComparePage() {
  const [params] = useSearchParams()
  const ids = (params.get('ids') ?? '').split(',').filter(Boolean).slice(0, 3)
  const job = params.get('job')
  const blind = useSession((s) => s.blindReview)
  const candidates = useQueries({ queries: ids.map((id) => getApiV1CandidatesRetrieveQueryOptions(id)) })
  const applications = useQueries({ queries: ids.map((id) => getApiV1ApplicationsListQueryOptions({ candidate: id })) })
  const appIds = applications.map((q) => {
    const results = q.data?.results ?? []
    return (job ? results.find((a) => a.requisition_id === job) : results[0])?.id
  })
  const assessments = useQueries({
    queries: appIds.map((appId) => ({ ...getApiV1ApplicationsAssessmentRetrieveQueryOptions(appId ?? ''), enabled: Boolean(appId), retry: false })),
  })
  if (candidates.some((q) => q.isLoading)) return <PageSkeleton />
  const people = candidates.map((q) => q.data).filter(Boolean) as CandidateDetail[]
  const matrices = assessments.map((q) => q.data as Assessment | undefined)
  const criteria = [...new Map(matrices.flatMap((m) => m?.criteria ?? []).map((c) => [c.criterion, c.level])).entries()]
  const label = (c: CandidateDetail, i: number) => blind ? `Candidate ${i + 1}` : c.full_name
  const skillSets = people.map((p) => new Set(p.skills.map((s) => s.name.toLowerCase())))
  const shared = [...(skillSets[0] ?? new Set<string>())].filter((s) => skillSets.every((set) => set.has(s)))

  return (
    <>
      <PageHeader crumbs={[{ label: 'Dashboard', to: '/' }, { label: 'Candidates', to: '/candidates' }, { label: 'Compare' }]}
        title="Compare candidates" description="Each requirement, side by side, with the line that shows it. Gaps come with a question to ask, not a penalty." />
      {people.length < 2 ? <Panel><EmptyState title="Pick two or three candidates">Select candidates on the Candidates page, then choose Compare.</EmptyState></Panel> : (
        <Panel flush>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] border-collapse text-sm">
              <thead>
                <tr>
                  <th className="w-48 p-4 text-left align-bottom text-xs font-semibold tracking-wide text-muted-foreground uppercase">Requirement</th>
                  {people.map((p, i) => (
                    <th key={p.id} className="border-l p-4 text-left align-bottom font-normal">
                      <Link to={`/candidates/${p.id}`} className="flex items-center gap-3 hover:text-violet">
                        <PersonAvatar name={blind ? p.id : p.full_name} size={40} />
                        <span><span className="font-heading block text-base font-semibold">{label(p, i)}</span>
                          <span className="text-xs text-muted-foreground">{p.skills.length} skills · {p.experience.length} roles</span></span>
                      </Link>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {criteria.length === 0 && <tr><td colSpan={people.length + 1}><EmptyState>No screening results yet for these candidates. Run matching on their job first.</EmptyState></td></tr>}
                {criteria.map(([name, level]) => (
                  <tr key={name} className="border-t align-top">
                    <td className="p-4"><p className="font-medium">{name}</p><p className="text-xs font-semibold tracking-wide text-muted-foreground uppercase">{level}</p></td>
                    {matrices.map((m, i) => {
                      const row = m?.criteria.find((c) => c.criterion === name)
                      const quote = ((row?.evidence ?? []) as Evidence[])[0]?.quote
                      return (
                        <td key={i} className="border-l p-4">
                          {row ? <>
                            <StatusBadge value={row.status} />
                            {quote && <p className="mt-2 text-[13px] leading-snug"><mark className="hl bg-transparent text-inherit">“{quote}”</mark></p>}
                            {!quote && row.question && <p className="mt-2 flex gap-1.5 text-[13px] text-muted-foreground"><CircleHelp className="mt-0.5 size-3.5 shrink-0" />{row.question}</p>}
                          </> : <span className="text-muted-foreground">Not screened</span>}
                        </td>
                      )
                    })}
                  </tr>
                ))}
                <tr className="border-t bg-muted/40 align-top">
                  <td className="p-4"><p className="font-medium">Skills in common</p></td>
                  <td colSpan={people.length} className="border-l p-4">
                    <div className="flex flex-wrap gap-1.5">{shared.length ? shared.map((s) => <span key={s} className="rounded-md bg-card px-2 py-0.5 text-xs font-medium capitalize ring-1 ring-border">{s}</span>) : <span className="text-muted-foreground">None</span>}</div>
                  </td>
                </tr>
                <tr className="border-t align-top">
                  <td className="p-4"><p className="font-medium">Only this candidate</p></td>
                  {people.map((p, i) => (
                    <td key={p.id} className="border-l p-4">
                      <div className="flex flex-wrap gap-1.5">
                        {[...skillSets[i]].filter((s) => !shared.includes(s)).map((s) => <span key={s} className="rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-violet capitalize">{s}</span>)}
                      </div>
                    </td>
                  ))}
                </tr>
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </>
  )
}
