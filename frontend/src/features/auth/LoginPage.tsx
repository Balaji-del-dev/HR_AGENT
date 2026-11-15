import { type FormEvent, useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { useQueryClient } from '@tanstack/react-query'
import { AlertCircle, Eye, EyeOff, Loader2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useSession } from '@/app/session'
import { apiV1AuthCsrfRetrieve, useApiV1AuthLoginCreate } from '@/shared/api/generated/auth/auth'
import { ApiError } from '@/shared/api/http'

const DEMO_PASSWORD = 'demo-pass-2026'
const DEMO = [
  ['acme_recruiter', 'Recruiter'], ['acme_hr_admin', 'HR admin'], ['acme_manager', 'Hiring manager'],
  ['acme_interviewer', 'Interviewer'], ['acme_finance', 'Finance'], ['acme_auditor', 'Auditor'],
]

/** Sign-in in the same look as the app: grey page, one white card, one purple action. */
export function LoginPage() {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const setTenant = useSession((s) => s.setTenant)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [show, setShow] = useState(false)
  const login = useApiV1AuthLoginCreate()
  useEffect(() => { void apiV1AuthCsrfRetrieve() }, [])

  const submit = (event: FormEvent) => {
    event.preventDefault()
    login.mutate({ data: { username, password } }, {
      onSuccess: (me) => { setTenant(me.memberships[0]?.tenant_id ?? null); void queryClient.invalidateQueries(); navigate('/') },
    })
  }

  return (
    <div className="flex min-h-svh flex-col bg-muted">
      <header className="mx-auto flex w-full max-w-[1080px] items-center gap-2.5 px-6 pt-8">
        <span className="grid size-8 place-items-center rounded-[7px] bg-primary text-base font-bold text-white">H</span>
        <span className="text-lg font-bold text-foreground">Hiring Desk</span>
      </header>

      <main className="flex flex-1 justify-center px-4 pt-10 pb-12 sm:pt-16">
        <div className="w-full max-w-[440px]">
          <form onSubmit={submit} noValidate
            className="rounded-lg border bg-card p-7 shadow-[0_15px_35px_-5px_rgb(50_50_93/0.08),0_5px_15px_rgb(0_0_0/0.04)] sm:p-10">
            <h1 className="text-2xl leading-8 font-bold text-foreground">Sign in to your account</h1>
            <p className="mt-1.5 text-sm text-muted-foreground">Use your work account to open your hiring desk.</p>

            {Boolean(login.error) && (
              <p role="alert" className="mt-6 flex gap-2 rounded-md bg-[#fde2e1] px-3 py-2.5 text-[13px] text-[#a1221a] dark:bg-destructive/15 dark:text-destructive">
                <AlertCircle className="mt-0.5 size-4 shrink-0" />
                {login.error instanceof ApiError ? login.error.message : 'Sign-in failed. Check your username and password.'}
              </p>
            )}

            <div className="mt-7 space-y-5">
              <div className="grid gap-1.5">
                <Label htmlFor="username" className="text-sm font-medium text-ink-2">Username</Label>
                <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required autoFocus className="h-10" />
              </div>
              <div className="grid gap-1.5">
                <Label htmlFor="password" className="text-sm font-medium text-ink-2">Password</Label>
                <div className="relative">
                  <Input id="password" type={show ? 'text' : 'password'} value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required className="h-10 pr-10" />
                  <Button type="button" variant="ghost" size="icon" className="absolute top-1/2 right-0.5 size-8 -translate-y-1/2 text-muted-foreground"
                    onClick={() => setShow(!show)} aria-label={show ? 'Hide password' : 'Show password'}>
                    {show ? <EyeOff /> : <Eye />}
                  </Button>
                </div>
              </div>
              <Button type="submit" size="lg" className="w-full" disabled={login.isPending || !username || !password}>
                {login.isPending ? <><Loader2 className="animate-spin" /> Signing in…</> : 'Sign in'}
              </Button>
            </div>

            <div className="mt-8 flex items-center gap-3 text-xs font-semibold text-muted-foreground">
              <span className="h-px flex-1 bg-border" />Demo accounts<span className="h-px flex-1 bg-border" />
            </div>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {DEMO.map(([user, role]) => (
                <button key={user} type="button" onClick={() => { setUsername(user); setPassword(DEMO_PASSWORD) }} aria-label={`${role} (${user})`}
                  className={`h-8 rounded-full border px-3.5 text-[13px] whitespace-nowrap font-medium transition outline-none focus-visible:ring-2 focus-visible:ring-ring ${username === user
                    ? 'border-primary bg-primary/[0.08] font-semibold text-primary dark:text-violet' : 'border-input bg-card text-ink-2 hover:border-primary/40 hover:text-foreground'}`}>
                  {role}
                </button>
              ))}
            </div>
            <p className="mt-3 text-center text-xs text-muted-foreground">Pick a role to fill in the form. Every demo account uses the password <span className="font-mono text-ink-2">{DEMO_PASSWORD}</span>.</p>
          </form>

          <p className="mt-6 text-center text-[13px] leading-5 text-muted-foreground">
            Agents read resumes and draft the next step. People make every decision, and each one is recorded with a reason.
          </p>
        </div>
      </main>
    </div>
  )
}
