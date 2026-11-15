import { MutationCache, QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider } from 'next-themes'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { RouterProvider } from 'react-router'
import { Toaster } from '@/components/ui/sonner'
import { TooltipProvider } from '@/components/ui/tooltip'
import './app/i18n'
import { router } from './app/router'
import { ApiError } from './shared/api/http'
import './index.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 10_000,
      retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 2,
    },
  },
  // After any change, refresh what is on screen. Server state stays the single source of truth.
  mutationCache: new MutationCache({
    onSuccess: (_data, _variables, _context, mutation) => {
      if (String(mutation.options.mutationKey?.[0] ?? '').includes('Logout')) return // sign-out clears the cache itself
      void queryClient.invalidateQueries()
    },
  }),
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false} disableTransitionOnChange>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={250}>
          <RouterProvider router={router} />
          <Toaster position="bottom-right" richColors closeButton />
        </TooltipProvider>
      </QueryClientProvider>
    </ThemeProvider>
  </StrictMode>,
)
