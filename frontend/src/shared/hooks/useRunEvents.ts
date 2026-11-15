import { useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import {
  getApiV1AgentRunsRetrieveQueryKey,
  useApiV1AgentRunsRetrieve,
} from '../api/generated/agent-runs/agent-runs'
import { type PushEvent, useSocket } from './realtime'

const ACTIVE = new Set(['queued', 'running'])

/**
 * Live view of one agent run: the WebSocket pushes step events into the query cache,
 * and polling GET /agent-runs/{id}/ takes over whenever the socket is down.
 */
export function useRunEvents(runId: string | null | undefined) {
  const queryClient = useQueryClient()
  const [events, setEvents] = useState<PushEvent[]>([])
  const connected = useSocket(runId ? `/ws/runs/${runId}/` : null, (event) => {
    setEvents((previous) => [...previous.slice(-50), event])
    if (runId) void queryClient.invalidateQueries({ queryKey: getApiV1AgentRunsRetrieveQueryKey(runId) })
  })
  const run = useApiV1AgentRunsRetrieve(runId ?? '', {
    query: {
      enabled: Boolean(runId),
      refetchInterval: (query) => {
        const status = query.state.data?.status
        if (!status || ACTIVE.has(status)) return connected ? 15_000 : 2_000
        return false
      },
    },
  })
  return { run: run.data, isLoading: run.isLoading, connected, events }
}
