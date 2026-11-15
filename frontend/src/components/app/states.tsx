import { useEffect, useState, type ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, CircleAlert, Inbox, WifiOff } from 'lucide-react'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ApiError } from '@/shared/api/http'

export function EmptyState({ title, children, action, icon }: { title?: string; children?: ReactNode; action?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-12 text-center">
      <div className="mb-3 grid size-11 place-items-center rounded-full border bg-muted text-muted-foreground [&_svg]:size-5">{icon ?? <Inbox />}</div>
      {title && <p className="text-base font-semibold">{title}</p>}
      {children && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function SuccessState({ title, children, action }: { title: string; children?: ReactNode; action?: ReactNode }) {
  return <EmptyState title={title} icon={<CheckCircle2 className="text-success" />} action={action}>{children}</EmptyState>
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message
  if (error instanceof Error) return error.message
  return 'Something went wrong.'
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const notFound = error instanceof ApiError && error.status === 404
  return (
    <EmptyState title={notFound ? 'Not found' : 'This could not be loaded'} icon={<CircleAlert className="text-destructive" />}
      action={onRetry && <Button variant="outline" onClick={onRetry}>Try again</Button>}>
      {notFound ? 'It does not exist, or you do not have access to it.' : errorMessage(error)}
    </EmptyState>
  )
}

export function ErrorAlert({ error }: { error: unknown }) {
  if (!error) return null
  const details = error instanceof ApiError ? Object.entries(error.details ?? {}) : []
  return (
    <Alert variant="destructive" className="mb-4">
      <AlertTriangle />
      <AlertTitle>{errorMessage(error)}</AlertTitle>
      {details.length > 0 && (
        <AlertDescription>
          <ul className="list-disc pl-4">{details.map(([k, v]) => <li key={k}>{k}: {Array.isArray(v) ? v.join(' ') : String(v)}</li>)}</ul>
        </AlertDescription>
      )}
    </Alert>
  )
}

export function SkeletonRows({ rows = 6 }: { rows?: number }) {
  return (
    <div className="space-y-3 p-5" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="size-8 rounded-full" />
          <div className="flex-1 space-y-1.5"><Skeleton className="h-3.5 w-2/5" /><Skeleton className="h-3 w-1/4" /></div>
          <Skeleton className="h-5 w-20 rounded-full" />
        </div>
      ))}
    </div>
  )
}

export function PageSkeleton() {
  return (
    <div className="space-y-6" aria-busy="true">
      <div className="space-y-2"><Skeleton className="h-3 w-40" /><Skeleton className="h-8 w-80" /></div>
      <div className="grid gap-4 md:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-32 rounded-2xl" />)}</div>
      <Skeleton className="h-72 rounded-2xl" />
    </div>
  )
}

export function OfflineBanner() {
  const [online, setOnline] = useState(navigator.onLine)
  useEffect(() => {
    const update = () => setOnline(navigator.onLine)
    window.addEventListener('online', update)
    window.addEventListener('offline', update)
    return () => { window.removeEventListener('online', update); window.removeEventListener('offline', update) }
  }, [])
  if (online) return null
  return (
    <Alert className="mb-4 border-warning/40 bg-warning/10">
      <WifiOff />
      <AlertTitle>You are offline</AlertTitle>
      <AlertDescription>What you see may be out of date, and changes will fail until you reconnect.</AlertDescription>
    </Alert>
  )
}
