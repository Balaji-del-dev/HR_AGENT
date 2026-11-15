import { cleanup, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { TooltipProvider } from '@/components/ui/tooltip'
import { DataTable } from '../components/app/data-table'
import { CriteriaMatrix } from '../features/review/CriteriaMatrix'
import type { CriterionResult } from '../shared/api/generated/model'
import { ReasonDialog } from '../components/app/dialogs'
import { StatusChip } from '../shared/ui/common'

afterEach(cleanup)

const criterion = (overrides: Partial<CriterionResult>): CriterionResult => ({
  id: crypto.randomUUID(), requirement_id: null, criterion: 'Python', level: 'mandatory', status: 'documented',
  model_status: 'documented', evidence: [{ span_id: 'doc_1:p1:0-10', quote: 'Built APIs in Python' }],
  rejected_evidence: [], validation_note: '', question: '', position: 0, ...overrides,
} as CriterionResult)

describe('CriteriaMatrix', () => {
  it('shows evidence quotes and validation changes, and no score', async () => {
    const onFocus = vi.fn()
    render(<TooltipProvider><CriteriaMatrix onFocus={onFocus} criteria={[
      criterion({}),
      criterion({ criterion: 'RAG', status: 'not_documented', model_status: 'documented', evidence: [],
        validation_note: 'The evidence did not hold up.', question: 'Ask about RAG.' }),
    ]} /></TooltipProvider>)
    await userEvent.click(screen.getByRole('button', { name: 'Show evidence for Python in the resume' }))
    expect(onFocus).toHaveBeenCalledWith('doc_1:p1:0-10')
    expect(screen.getByText('changed by validation')).toBeInTheDocument()
    expect(screen.getByText('Ask about RAG.')).toBeInTheDocument()
    expect(screen.queryByText(/score/i)).not.toBeInTheDocument()
  })
})

describe('ReasonDialog', () => {
  it('will not confirm without a reason', async () => {
    const onConfirm = vi.fn()
    render(<ReasonDialog open title="Reject" confirmLabel="Reject" onClose={() => {}} onConfirm={onConfirm} />)
    const confirm = screen.getByRole('button', { name: 'Reject' })
    expect(confirm).toBeDisabled()
    await userEvent.type(screen.getByLabelText(/Reason/), 'Role filled')
    await userEvent.click(confirm)
    expect(onConfirm).toHaveBeenCalledWith('Role filled')
  })
})

describe('StatusChip', () => {
  it('renders readable labels', () => {
    render(<StatusChip value="awaiting_review" />)
    expect(screen.getByText('Awaiting review')).toBeInTheDocument()
  })
})

describe('DataTable', () => {
  type Row = { id: string; name: string; status: string }
  const rows: Row[] = Array.from({ length: 23 }, (_, i) => ({ id: String(i), name: `Person ${i}`, status: i % 2 ? 'open' : 'closed' }))
  const table = () => render(
    <TooltipProvider>
      <DataTable rows={rows} rowKey={(r) => r.id} filterText={(r) => r.name} filterPlaceholder="Search people"
        facets={[{ key: 'status', label: 'Status', value: (r) => r.status }]}
        columns={[{ key: 'name', header: 'Name', sort: (r: Row) => r.name, cell: (r: Row) => r.name }, { key: 'status', header: 'Status', cell: (r: Row) => r.status }]} />
    </TooltipProvider>,
  )

  it('pages rows and reports the range', () => {
    table()
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(11)
  })

  it('searches, shows how many matched, and resets', async () => {
    table()
    await userEvent.type(screen.getByLabelText('Search people'), 'Person 2')
    expect(screen.getAllByRole('row')).toHaveLength(5) // header + Person 2, 20, 21, 22
    expect(screen.getByText(/filtered from 23/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /Reset/ }))
    expect(screen.getByText('Page 1 of 3')).toBeInTheDocument()
  })
})
