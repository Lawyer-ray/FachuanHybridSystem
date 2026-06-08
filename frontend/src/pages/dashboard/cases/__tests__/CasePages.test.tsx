import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { CaseListPage } from '../CaseListPage'
import { CaseNewPage } from '../CaseNewPage'
import { CaseDetailPage } from '../CaseDetailPage'
import { CaseEditPage } from '../CaseEditPage'

// Mock case feature components
vi.mock('@/features/cases/components/CaseList', () => ({
  CaseList: () => <div data-testid="case-list">CaseList</div>,
}))

vi.mock('@/features/cases/components/CaseForm', () => ({
  CaseForm: ({ mode, caseId }: { mode: string; caseId?: string }) => (
    <div data-testid="case-form">CaseForm-{mode}{caseId ? `-${caseId}` : ''}</div>
  ),
}))

vi.mock('@/features/cases/components/CaseDetail', () => ({
  CaseDetail: ({ caseId }: { caseId: string }) => (
    <div data-testid="case-detail">CaseDetail-{caseId}</div>
  ),
}))

describe('CaseListPage', () => {
  it('renders CaseList component', () => {
    render(
      <MemoryRouter>
        <CaseListPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('case-list')).toBeInTheDocument()
  })
})

describe('CaseNewPage', () => {
  it('renders CaseForm in create mode', () => {
    render(
      <MemoryRouter>
        <CaseNewPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('case-form')).toBeInTheDocument()
    expect(screen.getByText('CaseForm-create')).toBeInTheDocument()
  })
})

describe('CaseDetailPage', () => {
  it('renders CaseDetail with id from params', () => {
    render(
      <MemoryRouter initialEntries={['/admin/cases/123']}>
        <Routes>
          <Route path="/admin/cases/:id" element={<CaseDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('case-detail')).toBeInTheDocument()
    expect(screen.getByText('CaseDetail-123')).toBeInTheDocument()
  })
})

describe('CaseEditPage', () => {
  it('renders CaseForm in edit mode with id from params', () => {
    render(
      <MemoryRouter initialEntries={['/admin/cases/456/edit']}>
        <Routes>
          <Route path="/admin/cases/:id/edit" element={<CaseEditPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('case-form')).toBeInTheDocument()
    expect(screen.getByText('CaseForm-edit-456')).toBeInTheDocument()
  })
})
