/**
 * WebSockets with one-time tickets. Browsers cannot set auth headers on a WebSocket,
 * so each connection first exchanges the session for a ticket (POST /api/v1/ws-tickets/).
 * Connections reconnect with backoff; callers keep a polling fallback for runs.
 */
import { useEffect, useRef, useState } from 'react'
import { apiV1WsTicketsCreate } from '../api/generated/realtime/realtime'

export type PushEvent = { type: string; [key: string]: unknown }

export function useSocket(path: string | null, onEvent: (event: PushEvent) => void): boolean {
  const [connected, setConnected] = useState(false)
  const handler = useRef(onEvent)
  handler.current = onEvent

  useEffect(() => {
    if (!path) return
    let socket: WebSocket | null = null
    let stopped = false
    let attempt = 0
    let timer: number | undefined

    const connect = async () => {
      try {
        const { ticket } = await apiV1WsTicketsCreate()
        if (stopped) return
        const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
        socket = new WebSocket(`${scheme}://${window.location.host}${path}?ticket=${encodeURIComponent(ticket)}`)
        socket.onopen = () => {
          attempt = 0
          setConnected(true)
        }
        socket.onmessage = (message) => handler.current(JSON.parse(message.data) as PushEvent)
        socket.onclose = () => {
          setConnected(false)
          if (!stopped) schedule()
        }
      } catch {
        schedule()
      }
    }
    const schedule = () => {
      attempt += 1
      timer = window.setTimeout(connect, Math.min(30_000, 1000 * 2 ** Math.min(attempt, 5)))
    }
    void connect()
    return () => {
      stopped = true
      window.clearTimeout(timer)
      socket?.close()
    }
  }, [path])

  return connected
}
