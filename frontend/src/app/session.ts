/** Small client-only state (Zustand): the active tenant and UI preferences. Server data lives in TanStack Query. */
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface SessionState {
  tenantId: string | null
  blindReview: boolean
  railCollapsed: boolean
  setTenant: (tenantId: string | null) => void
  setBlindReview: (on: boolean) => void
  setRailCollapsed: (collapsed: boolean) => void
}

export const useSession = create<SessionState>()(
  persist(
    (set) => ({
      tenantId: null,
      blindReview: false,
      railCollapsed: false,
      setTenant: (tenantId) => set({ tenantId }),
      setBlindReview: (blindReview) => set({ blindReview }),
      setRailCollapsed: (railCollapsed) => set({ railCollapsed }),
    }),
    { name: 'hr-session' },
  ),
)
