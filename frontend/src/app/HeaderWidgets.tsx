import { useState } from 'react'
import { Link } from 'react-router'
import { useTheme } from 'next-themes'
import { useQueryClient } from '@tanstack/react-query'
import { Bell, Building2, Check, ChevronsUpDown, LogOut, Moon, Sun, UserRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { KeyValue } from '@/components/app/page'
import { PersonAvatar } from '@/components/app/people'
import type { ApprovalRequest } from '@/shared/api/generated/model'
import type { PushEvent } from '@/shared/hooks/realtime'
import { useMe } from '@/shared/hooks/useMe'
import { relativeTime } from '@/shared/ui/common'
import { useSession } from './session'

export function describeEvent(event: PushEvent): string {
  if (event.type === 'approval.requested') return `New approval: ${String(event.title ?? '')}`
  if (event.type === 'run.status') return `Agent “${String(event.kind ?? '').replaceAll('_', ' ')}” is ${String(event.status ?? '').replaceAll('_', ' ')}`
  if (event.type.startsWith('document.')) return `Resume ${String(event.status ?? '').replaceAll('_', ' ')}`
  return event.type
}

export function NotificationBell({ approvals, events, onClear }: { approvals: ApprovalRequest[]; events: (PushEvent & { at: number })[]; onClear: () => void }) {
  const count = approvals.length + events.length
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="ghost" size="icon" className="relative text-muted-foreground" aria-label={`Notifications, ${count}`}>
          <Bell />
          {count > 0 && <span className="absolute top-1 right-1 grid min-w-4 place-items-center rounded-full bg-primary px-1 text-[10px] leading-4 font-semibold text-white tabular ring-2 ring-background">{count}</span>}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[360px] p-0">
        <div className="border-b px-4 py-3"><p className="font-heading text-sm font-semibold">Waiting for you</p></div>
        <ul className="max-h-60 overflow-y-auto p-1.5">
          {approvals.length === 0 && <li className="px-3 py-3 text-sm text-muted-foreground">Nothing is waiting for your decision.</li>}
          {approvals.slice(0, 6).map((a) => (
            <li key={a.id}>
              <Link to={`/approvals/${a.id}`} className="block rounded-lg px-3 py-2 hover:bg-muted">
                <p className="text-sm font-medium">{a.title}</p>
                <p className="text-xs text-muted-foreground">{a.kind.replaceAll('_', ' ')} · {relativeTime(a.created_at)}</p>
              </Link>
            </li>
          ))}
        </ul>
        <div className="flex items-center border-t px-4 py-2.5">
          <p className="font-heading flex-1 text-sm font-semibold">Live updates</p>
          {events.length > 0 && <Button variant="ghost" size="sm" onClick={onClear}>Clear</Button>}
        </div>
        <ul className="max-h-48 overflow-y-auto p-1.5 pt-0">
          {events.length === 0 && <li className="px-3 pb-3 text-sm text-muted-foreground">Agent runs and uploads appear here as they happen.</li>}
          {events.map((e, i) => (
            <li key={i}>
              <Link to={e.run_id ? `/agents/${String(e.run_id)}` : e.approval_request_id ? `/approvals/${String(e.approval_request_id)}` : e.candidate_id ? `/candidates/${String(e.candidate_id)}` : '/'}
                className="block rounded-lg px-3 py-2 hover:bg-muted">
                <p className="text-sm">{describeEvent(e)}</p>
                <p className="text-xs text-muted-foreground">{new Date(e.at).toLocaleTimeString()}</p>
              </Link>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  )
}

export function TenantSwitcher() {
  const { me, membership } = useMe()
  const setTenant = useSession((s) => s.setTenant)
  const queryClient = useQueryClient()
  if (!me || !membership) return null
  const card = (
    <span className="flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left transition hover:bg-accent">
      <span className="grid size-7 place-items-center rounded-[7px] bg-primary text-white"><Building2 className="size-3.5" /></span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-bold text-foreground">{membership.tenant_name}</span>
        <span className="block truncate text-xs text-muted-foreground capitalize">{membership.roles.join(', ').replaceAll('_', ' ')}</span>
      </span>
      {me.memberships.length > 1 && <ChevronsUpDown className="size-4 text-muted-foreground" />}
    </span>
  )
  if (me.memberships.length < 2) return card
  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="w-full rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring">{card}</DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-56">
        <DropdownMenuLabel>Organisations</DropdownMenuLabel>
        {me.memberships.map((m) => (
          <DropdownMenuItem key={m.tenant_id} onClick={() => { setTenant(m.tenant_id); void queryClient.invalidateQueries() }}>
            {m.tenant_name}{m.tenant_id === membership.tenant_id && <Check className="ml-auto" />}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function UserMenu({ onSignOut }: { onSignOut: () => void }) {
  const { me, membership } = useMe()
  const { resolvedTheme, setTheme } = useTheme()
  const [profile, setProfile] = useState(false)
  if (!me) return null
  const dark = resolvedTheme === 'dark'
  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger className="ml-1 rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring" aria-label="Account menu">
          <PersonAvatar name={me.full_name} size={32} />
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-60">
          <DropdownMenuLabel className="font-normal">
            <p className="font-semibold">{me.full_name}</p>
            <p className="text-xs text-muted-foreground">{me.email}</p>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => setProfile(true)}><UserRound /> Profile</DropdownMenuItem>
          <DropdownMenuItem onClick={() => setTheme(dark ? 'light' : 'dark')}>{dark ? <Sun /> : <Moon />} {dark ? 'Light mode' : 'Dark mode'}</DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={onSignOut}><LogOut /> Sign out</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Dialog open={profile} onOpenChange={setProfile}>
        <DialogContent className="sm:max-w-sm">
          <div className="flex flex-col items-center gap-3 pt-2 text-center">
            <PersonAvatar name={me.full_name} size={72} />
            <div>
              <DialogTitle className="font-heading text-xl">{me.full_name}</DialogTitle>
              <p className="text-sm text-muted-foreground">{me.email}</p>
            </div>
            <div className="flex flex-wrap justify-center gap-1.5">
              {(membership?.roles ?? []).map((r) => <span key={r} className="rounded-full bg-primary/15 px-2.5 py-0.5 text-xs font-medium text-violet capitalize">{r.replaceAll('_', ' ')}</span>)}
            </div>
          </div>
          <div className="mt-2 rounded-xl border p-4">
            <KeyValue items={[
              ['Username', me.username],
              ['Organisation', membership?.tenant_name ?? '—'],
              ['Member of', me.memberships.map((m) => m.tenant_name).join(', ')],
              ['Sign-in', 'Session here; OIDC with MFA in production'],
            ]} />
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}
