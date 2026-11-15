import { Navigate, createBrowserRouter, useParams } from 'react-router'
import { LoginPage } from '../features/auth/LoginPage'
import { DashboardPage } from '../features/dashboard/DashboardPage'
import { AppShell } from './AppShell'
import { AuthGate } from './AuthGate'

// Pages load on first visit, so charts and the agent graph stay out of the first download.

function RunRedirect() {
  const { id = '' } = useParams()
  return <Navigate to={`/agents/${id}`} replace />
}

export const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    element: <AuthGate />,
    children: [
      {
        element: <AppShell />,
        children: [
          { path: '/', element: <DashboardPage /> },
          { path: '/requisitions', lazy: () => import('../features/requisitions/RequisitionsPage').then((m) => ({ Component: m.RequisitionsPage })) },
          { path: '/requisitions/:id', lazy: () => import('../features/requisitions/RequisitionDetailPage').then((m) => ({ Component: m.RequisitionDetailPage })) },
          { path: '/requisitions/:id/jd', lazy: () => import('../features/jd-studio/JdStudioPage').then((m) => ({ Component: m.JdStudioPage })) },
          { path: '/requisitions/:id/pipeline', lazy: () => import('../features/pipeline/PipelineBoardPage').then((m) => ({ Component: m.PipelineBoardPage })) },
          { path: '/requisitions/:id/review', lazy: () => import('../features/review/CandidateReviewPage').then((m) => ({ Component: m.CandidateReviewPage })) },
          { path: '/candidates', lazy: () => import('../features/candidates/CandidatesPage').then((m) => ({ Component: m.CandidatesPage })) },
          { path: '/candidates/compare', lazy: () => import('../features/candidates/CandidateComparePage').then((m) => ({ Component: m.CandidateComparePage })) },
          { path: '/candidates/:id', lazy: () => import('../features/candidates/CandidateDetailPage').then((m) => ({ Component: m.CandidateDetailPage })) },
          { path: '/approvals', lazy: () => import('../features/approvals/ApprovalsPage').then((m) => ({ Component: m.ApprovalsPage })) },
          { path: '/approvals/:id', lazy: () => import('../features/approvals/ApprovalDetailPage').then((m) => ({ Component: m.ApprovalDetailPage })) },
          { path: '/interviews', lazy: () => import('../features/interviews/InterviewsPage').then((m) => ({ Component: m.InterviewsPage })) },
          { path: '/interviews/:id/scorecard', lazy: () => import('../features/interviews/ScorecardPage').then((m) => ({ Component: m.ScorecardPage })) },
          { path: '/offers', lazy: () => import('../features/offers/OffersPage').then((m) => ({ Component: m.OffersPage })) },
          { path: '/assistant', lazy: () => import('../features/assistant/AssistantPage').then((m) => ({ Component: m.AssistantPage })) },
          { path: '/analytics', lazy: () => import('../features/analytics/AnalyticsPage').then((m) => ({ Component: m.AnalyticsPage })) },
          { path: '/settings', lazy: () => import('../features/admin/AdminPage').then((m) => ({ Component: m.AdminPage })) },  // /admin is Django's own admin site
          { path: '/agents', lazy: () => import('../features/agents/AgentMonitorPage').then((m) => ({ Component: m.AgentMonitorPage })) },
          { path: '/agents/:id', lazy: () => import('../features/runs/RunDetailPage').then((m) => ({ Component: m.RunDetailPage })) },
          { path: '/runs/:id', element: <RunRedirect /> },
        ],
      },
    ],
  },
])
