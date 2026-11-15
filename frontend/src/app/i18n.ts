import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

const en = {
  nav: {
    dashboard: 'Dashboard', requisitions: 'Requisitions', candidates: 'Candidates', approvals: 'Approvals',
    interviews: 'Interviews', offers: 'Offers', assistant: 'Assistant', analytics: 'Analytics', admin: 'Admin',
  },
  common: {
    save: 'Save', cancel: 'Cancel', submit: 'Submit', approve: 'Approve', reject: 'Reject',
    requestChanges: 'Request changes', reason: 'Reason', loading: 'Loading…', signOut: 'Sign out',
    nothingHere: 'Nothing here yet.', blindReview: 'Blind review',
  },
  stage: {
    applied: 'Applied', screening: 'Screening', shortlisted: 'Shortlisted', interview: 'Interview', offer: 'Offer',
    hired: 'Hired', rejected: 'Rejected', withdrawn: 'Withdrawn',
  },
}

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en } },
  lng: 'en',
  fallbackLng: 'en',
  interpolation: { escapeValue: false },
})

export default i18n
