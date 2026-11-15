import { useState, type ReactNode } from 'react'
import { useNavigate } from 'react-router'
import { Briefcase, UserRound } from 'lucide-react'
import { CommandDialog, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from '@/components/ui/command'
import { useApiV1CandidatesList } from '@/shared/api/generated/candidates/candidates'
import { useApiV1RequisitionsList } from '@/shared/api/generated/requisitions/requisitions'
import { useMe } from '@/shared/hooks/useMe'

export type PaletteEntry = { label: string; to: string; icon: ReactNode; group: string }

/** Ctrl/Cmd+K: go to any page, job or candidate you can see. */
export function CommandPalette({ open, onOpenChange, pages }: { open: boolean; onOpenChange: (open: boolean) => void; pages: PaletteEntry[] }) {
  const navigate = useNavigate()
  const { hasRole } = useMe()
  const [query, setQuery] = useState('')
  const recruiting = hasRole('hr_admin', 'recruiter', 'hiring_manager')
  const jobs = useApiV1RequisitionsList(undefined, { query: { enabled: open && recruiting } })
  const people = useApiV1CandidatesList(query.length > 1 ? { q: query } : undefined, { query: { enabled: open && recruiting } })
  const go = (to: string) => { onOpenChange(false); setQuery(''); navigate(to) }
  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title="Search" description="Jump to a page, job or candidate">
      <CommandInput placeholder="Type a page, job or candidate…" value={query} onValueChange={setQuery} />
      <CommandList>
        <CommandEmpty>No results.</CommandEmpty>
        <CommandGroup heading="Go to">
          {pages.map((p) => <CommandItem key={p.to} value={`page ${p.label}`} onSelect={() => go(p.to)}>{p.icon}{p.label}</CommandItem>)}
        </CommandGroup>
        {(jobs.data?.results ?? []).length > 0 && (
          <CommandGroup heading="Jobs">
            {jobs.data?.results?.map((r) => (
              <CommandItem key={r.id} value={`job ${r.title} ${r.department}`} onSelect={() => go(`/requisitions/${r.id}`)}>
                <Briefcase />{r.title}<span className="ml-auto text-xs text-muted-foreground">{r.department}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        {(people.data?.results ?? []).length > 0 && (
          <CommandGroup heading="Candidates">
            {people.data?.results?.slice(0, 8).map((c) => (
              <CommandItem key={c.id} value={`candidate ${c.full_name} ${c.email}`} onSelect={() => go(`/candidates/${c.id}`)}>
                <UserRound />{c.full_name}<span className="ml-auto text-xs text-muted-foreground">{c.source}</span>
              </CommandItem>
            ))}
          </CommandGroup>
        )}
      </CommandList>
    </CommandDialog>
  )
}
