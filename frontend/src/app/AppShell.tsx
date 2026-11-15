import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { AnimatePresence, motion } from 'motion/react'
import { toast } from 'sonner'
import {
  BarChart3, Bot, Briefcase, CalendarCheck, ChevronRight, ClipboardCheck, FileSignature, Home, Menu, PanelLeftClose, PanelLeftOpen, Search,
  Settings2, Sparkles, Users,
} from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { OfflineBanner } from '@/components/app/states'
import { useApiV1AgentRunsList } from '@/shared/api/generated/agent-runs/agent-runs'
import { useApiV1ApprovalsList } from '@/shared/api/generated/approvals/approvals'
import { useApiV1AuthLogoutCreate } from '@/shared/api/generated/auth/auth'
import { type Role, useMe } from '@/shared/hooks/useMe'
import { useNotifications } from '@/shared/hooks/useNotifications'
import { CommandPalette, type PaletteEntry } from './CommandPalette'
import { NotificationBell, TenantSwitcher, UserMenu, describeEvent } from './HeaderWidgets'
import { useSession } from './session'

const STAFF: Role[] = ['hr_admin', 'recruiter', 'hiring_manager', 'interviewer', 'finance_approver', 'auditor']
const RUN_VIEWERS: Role[] = ['hr_admin', 'recruiter', 'hiring_manager', 'auditor']
type NavItem = { to: string; key: string; label: string; icon: ReactNode; roles: Role[]; section: string }

// Navigation mirrors the server's roles so people only see what they can use. The API still enforces them.
export const NAV: NavItem[] = [
  { to: '/', key: 'dashboard', label: 'Home', icon: <Home />, roles: STAFF, section: '' },
  { to: '/assistant', key: 'assistant', label: 'AI Recruiter', icon: <Sparkles />, roles: ['hr_admin', 'recruiter', 'hiring_manager'], section: '' },
  { to: '/approvals', key: 'approvals', label: 'Approvals', icon: <ClipboardCheck />, roles: ['hr_admin', 'recruiter', 'hiring_manager', 'finance_approver', 'auditor'], section: '' },
  { to: '/requisitions', key: 'requisitions', label: 'Jobs', icon: <Briefcase />, roles: ['hr_admin', 'recruiter', 'hiring_manager'], section: 'Hiring' },
  { to: '/candidates', key: 'candidates', label: 'Candidates', icon: <Users />, roles: ['hr_admin', 'recruiter', 'hiring_manager'], section: 'Hiring' },
  { to: '/interviews', key: 'interviews', label: 'Interviews', icon: <CalendarCheck />, roles: ['hr_admin', 'recruiter', 'hiring_manager', 'interviewer'], section: 'Hiring' },
  { to: '/offers', key: 'offers', label: 'Offers', icon: <FileSignature />, roles: ['hr_admin', 'recruiter', 'finance_approver'], section: 'Hiring' },
  { to: '/agents', key: 'agents', label: 'Agent monitor', icon: <Bot />, roles: RUN_VIEWERS, section: 'Insights' },
  { to: '/analytics', key: 'analytics', label: 'Analytics', icon: <BarChart3 />, roles: ['hr_admin', 'recruiter', 'hiring_manager', 'auditor'], section: 'Insights' },
]
const SETTINGS: NavItem = { to: '/settings', key: 'admin', label: 'Settings', icon: <Settings2 />, roles: ['hr_admin', 'auditor'], section: '' }

function BrandMark({ size = 28 }: { size?: number }) {
  return <span className="grid shrink-0 place-items-center rounded-[7px] bg-primary font-bold text-white" style={{ width: size, height: size, fontSize: size * 0.5 }}>H</span>
}

function NavItemLink({ item, collapsed, onNavigate, badge }: { item: NavItem; collapsed: boolean; onNavigate?: () => void; badge?: number }) {
  const location = useLocation()
  const active = item.to === '/' ? location.pathname === '/' : location.pathname.startsWith(item.to)
  const link = (
    <NavLink to={item.to} onClick={onNavigate} aria-current={active ? 'page' : undefined}
      className={cn('relative flex h-[34px] items-center gap-2.5 rounded-md px-2.5 text-sm transition-colors outline-none focus-visible:ring-2 focus-visible:ring-ring',
        active ? 'bg-primary/[0.08] font-semibold text-primary dark:text-violet' : 'font-medium text-ink-2 hover:bg-accent hover:text-foreground',
        collapsed && 'justify-center px-0')}>
      <span className={cn('[&_svg]:size-4', active ? 'text-primary dark:text-violet' : 'text-muted-foreground')}>{item.icon}</span>
      {!collapsed && <span className="flex-1 truncate">{item.label}</span>}
      {badge !== undefined && badge > 0 && (
        <span className={cn('grid h-5 min-w-5 place-items-center rounded-full bg-primary px-1.5 text-xs font-semibold text-white tabular', collapsed && 'absolute -top-1 -right-1')}>{badge}</span>
      )}
    </NavLink>
  )
  return collapsed ? <Tooltip><TooltipTrigger asChild>{link}</TooltipTrigger><TooltipContent side="right">{item.label}</TooltipContent></Tooltip> : link
}

function SideNav({ collapsed, onNavigate, badge }: { collapsed: boolean; onNavigate?: () => void; badge: number }) {
  const { hasRole } = useMe()
  const items = NAV.filter((item) => hasRole(...item.roles))
  const sections = [...new Set(items.map((i) => i.section))]
  return (
    <nav aria-label="Main" className="flex flex-1 flex-col gap-[18px] overflow-y-auto px-3 py-1">
      {sections.map((section) => (
        <div key={section || 'main'} className="flex flex-col gap-0.5">
          {section && !collapsed && <p className="px-2.5 pb-1 text-xs font-semibold text-muted-foreground">{section}</p>}
          {items.filter((i) => i.section === section).map((item) => (
            <NavItemLink key={item.to} item={item} collapsed={collapsed} onNavigate={onNavigate} badge={item.key === 'approvals' ? badge : undefined} />
          ))}
        </div>
      ))}
    </nav>
  )
}

/** Live count of agent work, so people see at a glance whether anything is waiting on them. */
function AgentsStatus({ onNavigate }: { onNavigate?: () => void }) {
  const { hasRole } = useMe()
  const runs = useApiV1AgentRunsList(undefined, { query: { enabled: hasRole(...RUN_VIEWERS), refetchInterval: 10_000 } })
  if (!hasRole(...RUN_VIEWERS)) return null
  const all = runs.data?.results ?? []
  const running = all.filter((r) => r.status === 'running' || r.status === 'queued').length
  const waiting = all.filter((r) => r.status === 'awaiting_review').length
  return (
    <Link to="/agents" onClick={onNavigate} className="mb-2 flex items-center gap-2.5 rounded-lg border p-2.5 transition hover:bg-accent focus-visible:ring-2 focus-visible:ring-ring outline-none">
      <span className={cn('size-2 shrink-0 rounded-full', running ? 'pulse-ring bg-[#2b6fd6] text-[#2b6fd6]' : waiting ? 'bg-amber-400' : 'bg-[#2e8540]')} />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-[13px] font-semibold text-foreground">{running ? `${running} agent${running === 1 ? '' : 's'} running` : 'Agents idle'}</span>
        <span className="block truncate text-xs text-muted-foreground">{waiting ? `${waiting} draft${waiting === 1 ? '' : 's'} waiting for you` : 'Nothing waiting'}</span>
      </span>
      <ChevronRight className="size-3.5 text-muted-foreground" />
    </Link>
  )
}

function SidebarBody({ collapsed, badge, onNavigate }: { collapsed: boolean; badge: number; onNavigate?: () => void }) {
  const { me, membership, hasRole } = useMe()
  return (
    <>
      <div className={cn('px-3 pt-4 pb-5', collapsed && 'flex justify-center px-0')}>
        {collapsed ? <BrandMark /> : (me?.memberships.length ?? 0) > 1 ? <TenantSwitcher /> : (
          <div className="flex items-center gap-2.5 px-2 py-1.5">
            <BrandMark />
            <span className="min-w-0">
              <span className="block truncate text-sm font-bold text-foreground">{membership?.tenant_name ?? 'Recruiting'}</span>
              <span className="block text-xs text-muted-foreground">Hiring Desk</span>
            </span>
          </div>
        )}
      </div>
      <SideNav collapsed={collapsed} onNavigate={onNavigate} badge={badge} />
      <div className="mt-auto flex flex-col gap-0.5 px-3 pb-3">
        {!collapsed && <AgentsStatus onNavigate={onNavigate} />}
        {hasRole(...SETTINGS.roles) && <NavItemLink item={SETTINGS} collapsed={collapsed} onNavigate={onNavigate} />}
      </div>
    </>
  )
}

export function AppShell() {
  const { me, hasRole } = useMe()
  const { railCollapsed, setRailCollapsed } = useSession()
  const location = useLocation()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const [mobileOpen, setMobileOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const logout = useApiV1AuthLogoutCreate()
  const pending = useApiV1ApprovalsList({ status: 'pending' }, { query: { refetchInterval: 60_000 } })
  const decidable = pending.data?.results?.filter((a) => a.can_decide) ?? []
  const { history, clearHistory } = useNotifications(Boolean(me), (event) => toast(describeEvent(event)))

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const typing = e.target instanceof HTMLElement && ['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)
      if (((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') || (e.key === '/' && !typing)) { e.preventDefault(); setPaletteOpen(true) }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  const entries = useMemo<PaletteEntry[]>(() => [...NAV, SETTINGS].filter((i) => hasRole(...i.roles))
    .map((i) => ({ label: i.label, to: i.to, icon: i.icon, group: 'Go to' })), [hasRole])
  const signOut = () => logout.mutate(undefined, { onSuccess: () => { queryClient.clear(); navigate('/login') } })

  return (
    <div className="flex min-h-svh bg-background">
      <aside className={cn('sticky top-0 hidden h-svh shrink-0 flex-col border-r bg-sidebar transition-[width] duration-200 md:flex', railCollapsed ? 'w-[68px]' : 'w-[240px]')}>
        <SidebarBody collapsed={railCollapsed} badge={decidable.length} />
      </aside>

      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="flex w-[260px] flex-col gap-0 bg-sidebar p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <SidebarBody collapsed={false} badge={decidable.length} onNavigate={() => setMobileOpen(false)} />
        </SheetContent>
      </Sheet>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-[60px] items-center gap-2 border-b bg-background px-4 md:px-10">
          <Button variant="ghost" size="icon" className="md:hidden" onClick={() => setMobileOpen(true)} aria-label="Open navigation"><Menu /></Button>
          <Button variant="ghost" size="icon" className="hidden text-muted-foreground md:inline-flex" onClick={() => setRailCollapsed(!railCollapsed)} aria-label={railCollapsed ? 'Expand sidebar' : 'Collapse sidebar'}>
            {railCollapsed ? <PanelLeftOpen /> : <PanelLeftClose />}
          </Button>
          <button type="button" onClick={() => setPaletteOpen(true)}
            className="flex h-9 min-w-0 flex-1 items-center gap-2 rounded-lg bg-muted px-3 text-left text-sm text-muted-foreground transition hover:bg-[#eef1f5] focus-visible:ring-2 focus-visible:ring-ring outline-none sm:max-w-[440px] dark:hover:bg-accent">
            <Search className="size-4" />
            <span className="flex-1 truncate">Search</span>
            <kbd className="hidden rounded border bg-card px-1.5 font-mono text-xs text-muted-foreground sm:inline">/</kbd>
          </button>
          <div className="hidden flex-1 sm:block" />
          <NotificationBell approvals={decidable} events={history} onClear={clearHistory} />
          <UserMenu onSignOut={signOut} />
        </header>
        <main className="w-full max-w-[1240px] flex-1 px-4 py-7 md:px-10 md:pb-12">
          <OfflineBanner />
          <AnimatePresence mode="wait">
            <motion.div key={location.pathname} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} transition={{ duration: 0.12 }}>
              <Outlet />
            </motion.div>
          </AnimatePresence>
        </main>
      </div>
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} pages={entries} />
      {!me && <Link to="/login" className="sr-only">Sign in</Link>}
    </div>
  )
}
