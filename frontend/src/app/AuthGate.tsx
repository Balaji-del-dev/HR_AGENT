import { useEffect } from 'react'
import { Navigate, Outlet } from 'react-router'
import { ApiError } from '../shared/api/http'
import { useMe } from '../shared/hooks/useMe'
import { Loading } from '../shared/ui/common'
import { useSession } from './session'

/** Signed-in users only. Picks a tenant when the stored one is no longer valid. */
export function AuthGate() {
  const { me, isLoading, error } = useMe()
  const { tenantId, setTenant } = useSession()
  useEffect(() => {
    if (me && !me.memberships.some((m) => m.tenant_id === tenantId)) setTenant(me.memberships[0]?.tenant_id ?? null)
  }, [me, tenantId, setTenant])
  if (isLoading) return <Loading />
  if (error instanceof ApiError && (error.status === 401 || error.status === 403)) return <Navigate to="/login" replace />
  if (!me) return <Navigate to="/login" replace />
  return <Outlet />
}
