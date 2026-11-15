import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { type PushEvent, useSocket } from './realtime'

/** Approvals and run alerts for the signed-in user; refreshes the lists that changed. */
export function useNotifications(enabled: boolean, onEvent?: (event: PushEvent) => void) {
  const queryClient = useQueryClient()
  const [latest, setLatest] = useState<PushEvent | null>(null)
  const [history, setHistory] = useState<(PushEvent & { at: number })[]>([])
  useSocket(enabled ? '/ws/notifications/' : null, (event) => {
    setLatest(event)
    onEvent?.(event)
    setHistory((items) => [{ ...event, at: Date.now() }, ...items].slice(0, 20))
    const roots = event.type.startsWith('approval') ? ['/api/v1/approvals/'] : ['/api/v1/agent-runs/', '/api/v1/approvals/']
    if (event.type.startsWith('document')) roots.push('/api/v1/candidates/', '/api/v1/documents/')
    void queryClient.invalidateQueries({
      predicate: (query) => roots.some((root) => String(query.queryKey[0] ?? '').startsWith(root)),
    })
  })
  return { latest, history, clear: () => setLatest(null), clearHistory: () => setHistory([]) }
}
