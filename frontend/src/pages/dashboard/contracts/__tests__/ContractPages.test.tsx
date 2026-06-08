import { render, screen } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import ContractListPage from '../ContractListPage'
import ContractNewPage from '../ContractNewPage'
import ContractDetailPage from '../ContractDetailPage'
import ContractEditPage from '../ContractEditPage'

// Mock contract feature components
vi.mock('@/features/contracts/components/ContractList', () => ({
  ContractList: () => <div data-testid="contract-list">ContractList</div>,
}))

vi.mock('@/features/contracts/components/ContractForm', () => ({
  ContractForm: ({ mode }: { mode: string }) => (
    <div data-testid="contract-form">ContractForm-{mode}</div>
  ),
}))

vi.mock('@/features/contracts/components/ContractDetail', () => ({
  ContractDetail: ({ contractId }: { contractId: string }) => (
    <div data-testid="contract-detail">ContractDetail-{contractId}</div>
  ),
}))

vi.mock('@/features/contracts/hooks/use-contract', () => ({
  useContract: vi.fn().mockReturnValue({
    data: { id: '1', name: 'Test Contract' },
    isLoading: false,
  }),
}))

vi.mock('lucide-react', () => ({
  ArrowLeft: (props: Record<string, unknown>) => <svg data-testid="arrow-left" {...props} />,
  FileWarning: (props: Record<string, unknown>) => <svg data-testid="file-warning" {...props} />,
}))

vi.mock('@/components/ui/skeleton', () => ({
  Skeleton: (props: Record<string, unknown>) => <div data-testid="skeleton" {...props} />,
}))

describe('ContractListPage', () => {
  it('renders ContractList component', () => {
    render(
      <MemoryRouter>
        <ContractListPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('contract-list')).toBeInTheDocument()
  })
})

describe('ContractNewPage', () => {
  it('renders ContractForm in create mode', () => {
    render(
      <MemoryRouter>
        <ContractNewPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('contract-form')).toBeInTheDocument()
    expect(screen.getByText('ContractForm-create')).toBeInTheDocument()
  })

  it('renders page title', () => {
    render(
      <MemoryRouter>
        <ContractNewPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('新建合同')).toBeInTheDocument()
  })
})

describe('ContractDetailPage', () => {
  it('renders ContractDetail with id from params', () => {
    render(
      <MemoryRouter initialEntries={['/admin/contracts/5']}>
        <Routes>
          <Route path="/admin/contracts/:id" element={<ContractDetailPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('contract-detail')).toBeInTheDocument()
    expect(screen.getByText('ContractDetail-5')).toBeInTheDocument()
  })
})

describe('ContractEditPage', () => {
  it('renders ContractForm in edit mode', () => {
    render(
      <MemoryRouter initialEntries={['/admin/contracts/1/edit']}>
        <Routes>
          <Route path="/admin/contracts/:id/edit" element={<ContractEditPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByTestId('contract-form')).toBeInTheDocument()
    expect(screen.getByText('ContractForm-edit')).toBeInTheDocument()
  })

  it('renders page title with contract name', () => {
    render(
      <MemoryRouter initialEntries={['/admin/contracts/1/edit']}>
        <Routes>
          <Route path="/admin/contracts/:id/edit" element={<ContractEditPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('编辑合同：Test Contract')).toBeInTheDocument()
  })
})
