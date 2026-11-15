import { type ReactNode, useMemo, useState } from 'react'
import { ArrowDown, ArrowUp, Check, ChevronDown, ChevronsUpDown, Download, PlusCircle, Search, Settings2, X } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList, CommandSeparator } from '@/components/ui/command'
import {
  DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { EmptyState, SkeletonRows } from './states'

type Primitive = string | number | null | undefined

export type Column<T> = {
  key: string
  header: string
  cell: (row: T) => ReactNode
  /** Makes the column sortable. */
  sort?: (row: T) => Primitive
  /** Value written to CSV export; falls back to the sort value. */
  csv?: (row: T) => Primitive
  className?: string
  hide?: 'sm' | 'md' | 'lg'
  align?: 'right' | 'center'
  /** Listed in the Columns menu so people can hide it. Defaults to true for named columns after the first. */
  hideable?: boolean
}

/** A filter built from the values present in the rows, with live counts. */
export type Facet<T> = {
  key: string
  label: string
  value: (row: T) => string | string[] | null | undefined
  format?: (value: string) => ReactNode
}

const HIDE = { sm: 'hidden sm:table-cell', md: 'hidden md:table-cell', lg: 'hidden lg:table-cell' }
const pretty = (v: string) => { const t = v.replaceAll('_', ' '); return t.charAt(0).toUpperCase() + t.slice(1) }
const valuesOf = <T,>(facet: Facet<T>, row: T): string[] => {
  const v = facet.value(row)
  return (Array.isArray(v) ? v : [v]).filter((x): x is string => Boolean(x))
}

/** Dashed "+ Filter" pill; once used it turns solid and shows what it filters by. */
function FacetFilter<T>({ facet, rows, selected, onChange }: { facet: Facet<T>; rows: T[]; selected: Set<string>; onChange: (next: Set<string>) => void }) {
  const counts = useMemo(() => {
    const map = new Map<string, number>()
    rows.forEach((r) => valuesOf(facet, r).forEach((v) => map.set(v, (map.get(v) ?? 0) + 1)))
    selected.forEach((v) => { if (!map.has(v)) map.set(v, 0) })
    return [...map.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
  }, [rows, facet, selected])
  const label = (v: string) => facet.format?.(v) ?? pretty(v)
  const active = selected.size > 0
  return (
    <Popover>
      <div className={cn('inline-flex h-7 items-center rounded-full border bg-card text-[13px] font-medium text-ink-2',
        active ? 'border-input' : 'border-dashed border-[#c0c8d2] dark:border-input')}>
        {active && (
          <button type="button" aria-label={`Clear ${facet.label} filter`} onClick={() => onChange(new Set())}
            className="grid size-7 place-items-center rounded-full text-muted-foreground hover:text-foreground">
            <X className="size-3" />
          </button>
        )}
        <PopoverTrigger asChild>
          <button type="button" className={cn('inline-flex h-full items-center gap-1.5 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring', active ? 'pr-2.5' : 'px-2.5')}>
            {!active && <PlusCircle className="size-3.5 text-muted-foreground" />}
            {facet.label}
            {active && (
              <>
                <span className="h-3.5 w-px bg-input" />
                <span className="max-w-48 truncate font-semibold text-primary dark:text-violet">{selected.size > 2 ? `${selected.size} selected` : [...selected].map((v) => (facet.format ? v : pretty(v))).join(', ')}</span>
                <ChevronDown className="size-3.5 text-muted-foreground" />
              </>
            )}
          </button>
        </PopoverTrigger>
      </div>
      <PopoverContent className="w-60 p-0" align="start">
        <Command>
          <CommandInput placeholder={`Filter by ${facet.label.toLowerCase()}`} />
          <CommandList>
            <CommandEmpty>No values.</CommandEmpty>
            <CommandGroup>
              {counts.map(([value, count]) => {
                const on = selected.has(value)
                return (
                  <CommandItem key={value} value={value} onSelect={() => {
                    const next = new Set(selected)
                    if (on) next.delete(value)
                    else next.add(value)
                    onChange(next)
                  }}>
                    <span className={cn('grid size-4 place-items-center rounded-[4px] border', on ? 'border-primary bg-primary text-white' : 'border-input')}>
                      {on && <Check className="size-3" />}
                    </span>
                    <span className="flex-1 truncate">{label(value)}</span>
                    <span className="tabular text-xs text-muted-foreground">{count}</span>
                  </CommandItem>
                )
              })}
            </CommandGroup>
            {active && (
              <>
                <CommandSeparator />
                <CommandGroup>
                  <CommandItem onSelect={() => onChange(new Set())} className="justify-center text-center">Clear filter</CommandItem>
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  )
}

function toCsv<T>(rows: T[], columns: Column<T>[]): string {
  const cols = columns.filter((c) => c.header && (c.csv || c.sort))
  const esc = (v: Primitive) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replaceAll('"', '""')}"` : s
  }
  return [cols.map((c) => esc(c.header)).join(','), ...rows.map((r) => cols.map((c) => esc((c.csv ?? c.sort)?.(r))).join(','))].join('\n')
}

/**
 * The list table used across the app: search, "+ Filter" pills with counts, sortable headers,
 * a column picker, CSV export and paging. Rows open on click or Enter.
 */
export function DataTable<T>({
  rows, columns, rowKey, loading, onOpen, filterText, filterPlaceholder = 'Search', toolbar, empty, initialSort, pageSize = 10,
  facets = [], exportName, activeKey, noun = 'results',
}: {
  rows: readonly T[] | undefined
  columns: Column<T>[]
  rowKey: (row: T) => string
  loading?: boolean
  onOpen?: (row: T) => void
  filterText?: (row: T) => string
  filterPlaceholder?: string
  toolbar?: ReactNode
  empty?: ReactNode
  initialSort?: { key: string; desc?: boolean }
  pageSize?: number
  facets?: Facet<T>[]
  /** File name for the Export button; omit to hide it. */
  exportName?: string
  /** Key of a row to mark as selected. */
  activeKey?: string | null
  /** What the rows are, for the result count ("1–10 of 40 jobs"). */
  noun?: string
}) {
  const [query, setQuery] = useState('')
  const [sort, setSort] = useState(initialSort)
  const [page, setPage] = useState(0)
  const [picked, setPicked] = useState<Record<string, Set<string>>>({})
  const [hidden, setHidden] = useState<Set<string>>(new Set())

  const all = useMemo(() => [...(rows ?? [])], [rows])
  const matches = (row: T, except?: string) => {
    if (query && filterText && !filterText(row).toLowerCase().includes(query.toLowerCase())) return false
    return facets.every((f) => {
      if (f.key === except) return true
      const sel = picked[f.key]
      return !sel || sel.size === 0 || valuesOf(f, row).some((v) => sel.has(v))
    })
  }
  const data = (() => {
    const out = all.filter((r) => matches(r))
    const col = columns.find((c) => c.key === sort?.key)
    if (col?.sort && sort) {
      const get = col.sort
      out.sort((a, b) => {
        const x = get(a) ?? ''
        const y = get(b) ?? ''
        const r = typeof x === 'number' && typeof y === 'number' ? x - y : String(x).localeCompare(String(y), undefined, { numeric: true })
        return sort.desc ? -r : r
      })
    }
    return out
  })()

  const filtered = Boolean(query) || Object.values(picked).some((s) => s.size > 0)
  const visible = columns.filter((c) => !hidden.has(c.key))
  const hideable = columns.filter((c, i) => c.header && (c.hideable ?? i > 0))
  const pages = Math.max(1, Math.ceil(data.length / pageSize))
  const current = Math.min(page, pages - 1)
  const slice = data.slice(current * pageSize, current * pageSize + pageSize)
  const reset = () => { setQuery(''); setPicked({}); setPage(0) }
  const download = () => {
    const blob = new Blob([toCsv(data, visible)], { type: 'text/csv;charset=utf-8' })
    const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(blob), download: `${exportName}.csv` })
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <div className="min-w-0">
      <div className="mb-3 flex flex-col gap-2.5 lg:flex-row lg:items-center">
        <div className="flex flex-1 flex-wrap items-center gap-2">
          {filterText && (
            <label className="relative w-full sm:w-64">
              <Search className="pointer-events-none absolute top-1/2 left-2.5 size-3.5 -translate-y-1/2 text-muted-foreground" />
              <input value={query} onChange={(e) => { setQuery(e.target.value); setPage(0) }} placeholder={filterPlaceholder} aria-label={filterPlaceholder}
                className="h-8 w-full rounded-[7px] border border-transparent bg-muted pr-3 pl-8 text-[13px] text-foreground outline-none placeholder:text-muted-foreground focus:border-ring focus:bg-card" />
            </label>
          )}
          {facets.map((f) => (
            <FacetFilter key={f.key} facet={f} rows={all.filter((r) => matches(r, f.key))} selected={picked[f.key] ?? new Set()}
              onChange={(next) => { setPicked({ ...picked, [f.key]: next }); setPage(0) }} />
          ))}
          {filtered && <Button variant="ghost" size="sm" className="h-7 text-[13px] text-primary dark:text-violet" onClick={reset}>Reset <X /></Button>}
          {toolbar}
        </div>
        <div className="flex items-center gap-2">
          {hideable.length > 1 && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild><Button variant="outline" size="sm"><Settings2 /> Edit columns</Button></DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuLabel>Show columns</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {hideable.map((c) => (
                  <DropdownMenuCheckboxItem key={c.key} checked={!hidden.has(c.key)} onSelect={(e) => e.preventDefault()}
                    onCheckedChange={(on) => { const next = new Set(hidden); if (on) next.delete(c.key); else next.add(c.key); setHidden(next) }}>
                    {c.header}
                  </DropdownMenuCheckboxItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          {exportName && <Button variant="outline" size="sm" onClick={download} disabled={data.length === 0}><Download /> Export</Button>}
        </div>
      </div>

      {loading ? <SkeletonRows /> : data.length === 0 ? (
        <div className="border-t">
          {filtered
            ? <EmptyState title="No matches" icon={<Search />} action={<Button variant="outline" onClick={reset}>Clear filters</Button>}>Nothing matches these filters.</EmptyState>
            : (empty ?? <EmptyState title="Nothing here yet" />)}
        </div>
      ) : (
        <>
          <Table>
            <TableHeader>
              <TableRow className="hover:bg-transparent">
                {visible.map((c) => (
                  <TableHead key={c.key} aria-sort={sort?.key === c.key ? (sort.desc ? 'descending' : 'ascending') : undefined}
                    className={cn('text-[13px] first:pl-2 last:pr-2', c.align === 'right' && 'text-right', c.align === 'center' && 'text-center', c.hide && HIDE[c.hide], c.className)}>
                    {c.sort ? (
                      <button type="button" className={cn('inline-flex items-center gap-1 rounded outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring', sort?.key === c.key && 'text-foreground')}
                        onClick={() => setSort({ key: c.key, desc: sort?.key === c.key ? !sort.desc : false })}>
                        {c.header}
                        {sort?.key === c.key ? (sort.desc ? <ArrowDown className="size-3" /> : <ArrowUp className="size-3" />) : <ChevronsUpDown className="size-3 opacity-40" />}
                      </button>
                    ) : c.header}
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {slice.map((row) => {
                const key = rowKey(row)
                return (
                  <TableRow key={key} tabIndex={onOpen ? 0 : undefined} data-state={activeKey === key ? 'selected' : undefined}
                    onClick={onOpen ? () => onOpen(row) : undefined}
                    onKeyDown={onOpen ? (e) => { if (e.key === 'Enter') onOpen(row) } : undefined}
                    className={cn(onOpen && 'cursor-pointer focus-visible:bg-accent focus-visible:outline-none')}>
                    {visible.map((c) => (
                      <TableCell key={c.key} className={cn('h-[52px] text-sm text-ink-2 first:pl-2 last:pr-2', c.align === 'right' && 'text-right', c.align === 'center' && 'text-center', c.hide && HIDE[c.hide], c.className)}>{c.cell(row)}</TableCell>
                    ))}
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
          <div className="mt-3 flex flex-wrap items-center gap-3 text-[13px] text-muted-foreground">
            <p className="tabular flex-1">
              <span className="font-semibold text-foreground">{current * pageSize + 1}–{Math.min(data.length, (current + 1) * pageSize)}</span> of {data.length} {noun}
              {filtered && all.length !== data.length ? ` (filtered from ${all.length})` : ''}
            </p>
            <span className="tabular">Page {current + 1} of {pages}</span>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" disabled={current === 0} onClick={() => setPage(current - 1)}>Previous</Button>
              <Button variant="outline" size="sm" disabled={current >= pages - 1} onClick={() => setPage(current + 1)}>Next</Button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
