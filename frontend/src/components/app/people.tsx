import { cn } from '@/lib/utils'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'

const GRADIENTS = [
  ['#5e5be8', '#5e5be8'], ['#0f8c7e', '#0f8c7e'], ['#c7357a', '#c7357a'], ['#2b6fd6', '#2b6fd6'],
  ['#7c4ddb', '#7c4ddb'], ['#2e8540', '#2e8540'], ['#c9372c', '#c9372c'], ['#e5631b', '#e5631b'],
]

export function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return ((parts[0]?.[0] ?? '?') + (parts.length > 1 ? parts[parts.length - 1][0] : '')).toUpperCase()
}

function pick(seed: string): string[] {
  let hash = 0
  for (const ch of seed) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
  return GRADIENTS[hash % GRADIENTS.length]
}

/** Initials on the person's own gradient. Blind review passes a neutral seed instead of a name. */
export function PersonAvatar({ name, size = 32, label, className }: { name: string; size?: number; label?: string; className?: string }) {
  const [from, to] = pick(name)
  return (
    <span aria-hidden={!label} aria-label={label} className={cn('inline-grid shrink-0 place-items-center rounded-full font-semibold text-white select-none', className)}
      style={{ width: size, height: size, fontSize: size * 0.38, background: `linear-gradient(135deg, ${from}, ${to})` }}>
      {initials(name)}
    </span>
  )
}

export function PeopleStack({ names, max = 4 }: { names: string[]; max?: number }) {
  const shown = names.slice(0, max)
  return (
    <div className="flex -space-x-2">
      {shown.map((n, i) => (
        <Tooltip key={`${n}-${i}`}>
          <TooltipTrigger asChild><span className="rounded-full ring-2 ring-background"><PersonAvatar name={n} size={28} /></span></TooltipTrigger>
          <TooltipContent>{n}</TooltipContent>
        </Tooltip>
      ))}
      {names.length > max && <span className="grid size-7 place-items-center rounded-full bg-muted text-xs font-semibold ring-2 ring-background">+{names.length - max}</span>}
    </div>
  )
}
