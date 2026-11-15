import { useApiV1AuthMeRetrieve } from '../api/generated/auth/auth'
import { useSession } from '../../app/session'

export type Role = 'hr_admin' | 'recruiter' | 'hiring_manager' | 'interviewer' | 'finance_approver' | 'auditor'

/** The signed-in user, the active tenant membership and a role check that mirrors the server. */
export function useMe() {
  const query = useApiV1AuthMeRetrieve({ query: { retry: false, staleTime: 60_000 } })
  const tenantId = useSession((s) => s.tenantId)
  const memberships = query.data?.memberships ?? []
  const active = memberships.find((m) => m.tenant_id === tenantId) ?? memberships[0]
  const roles = new Set((active?.roles ?? []) as Role[])
  return {
    ...query,
    me: query.data,
    membership: active,
    roles,
    hasRole: (...wanted: Role[]) => wanted.some((role) => roles.has(role)),
  }
}
