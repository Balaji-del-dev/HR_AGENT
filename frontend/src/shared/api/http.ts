/**
 * The one fetch wrapper every generated hook uses.
 *
 * - Sends the Django session cookie and the CSRF token on unsafe methods.
 * - Sends X-Tenant-ID for users who belong to more than one tenant.
 * - Turns the API's error shape {"error": {code, message, details}} into ApiError.
 */
import { useSession } from '../../app/session'

export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, unknown>

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

function cookie(name: string): string | undefined {
  return document.cookie
    .split('; ')
    .find((part) => part.startsWith(`${name}=`))
    ?.split('=')[1]
}

const UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])

export async function apiFetch<T>(url: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? 'GET').toUpperCase()
  const headers = new Headers(options.headers)
  const tenantId = useSession.getState().tenantId
  if (tenantId) headers.set('X-Tenant-ID', tenantId)
  if (UNSAFE.has(method)) {
    const csrf = cookie('csrftoken')
    if (csrf) headers.set('X-CSRFToken', csrf)
  }
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }
  const response = await fetch(url, { ...options, method, headers, credentials: 'same-origin' })
  if (response.status === 204) return undefined as T
  const text = await response.text()
  const body = text ? JSON.parse(text) : undefined
  if (!response.ok) {
    const error = body?.error ?? {}
    const detail = typeof body?.detail === 'string' ? body.detail : undefined
    throw new ApiError(response.status, error.code ?? 'error', error.message ?? detail ?? response.statusText, error.details)
  }
  return body as T
}

export default apiFetch
