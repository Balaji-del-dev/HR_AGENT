import type { ReactNode } from 'react'
import { Briefcase, CalendarDays, ClipboardCheck, FileText, Mail, Wallet } from 'lucide-react'

/** One icon and tint per kind of approval, used in the inbox, the dashboard queue and detail pages. */
export const KIND_ICON: Record<string, ReactNode> = {
  requisition: <Briefcase />, job_description: <FileText />, email: <Mail />, offer: <Wallet />,
  shortlist_review: <ClipboardCheck />, interview_schedule: <CalendarDays />,
}
export const KIND_TINT: Record<string, string> = {
  requisition: 'bg-primary/18 text-violet', job_description: 'bg-primary/18 text-violet', email: 'bg-info/15 text-info',
  offer: 'bg-success/15 text-success', shortlist_review: 'bg-pink/15 text-pink', interview_schedule: 'bg-warning/15 text-warning',
}
export const KIND_LABEL: Record<string, string> = {
  requisition: 'Requisition', job_description: 'Job description', email: 'Email', offer: 'Offer',
  shortlist_review: 'Shortlist', interview_schedule: 'Interview time',
}
