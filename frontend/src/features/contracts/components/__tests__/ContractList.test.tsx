vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_CONTRACTS: '/admin/contracts', ADMIN_CONTRACT_NEW: '/admin/contracts/new' },
}))

vi.mock('@/hooks/use-paginated-list', () => ({
  usePaginatedList: vi.fn(),
}))

vi.mock('../../api', () => ({
  contractApi: { list: vi.fn() },
}))

vi.mock('../ContractFilters', () => ({
  ContractFilters: () => <div data-testid="contract-filters" />,
}))

vi.mock('../ContractTable', () => ({
  ContractTable: ({ contracts, isLoading }: any) => (
    <div data-testid="contract-table">{isLoading ? 'loading' : `${contracts.length} contracts`}</div>
  ),
}))

vi.mock('@/components/shared/PageFooter', () => ({
  PageFooter: ({ stats }: any) => <div data-testid="page-footer">{stats?.[0]?.value}</div>,
}))

import { render, screen } from '@testing-library/react'
import { usePaginatedList } from '@/hooks/use-paginated-list'
import { ContractList } from '../ContractList'

const mockUsePaginatedList = usePaginatedList as unknown as ReturnType<typeof vi.fn>

describe('ContractList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUsePaginatedList.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: false,
      page: 1,
      setPage: vi.fn(),
      withPageReset: (fn: any) => fn,
    })
  })

  it('renders filters', () => {
    render(<ContractList />)
    expect(screen.getByTestId('contract-filters')).toBeInTheDocument()
  })

  it('renders create button', () => {
    render(<ContractList />)
    expect(screen.getByText('新建合同')).toBeInTheDocument()
  })

  it('renders table', () => {
    render(<ContractList />)
    expect(screen.getByTestId('contract-table')).toBeInTheDocument()
  })

  it('renders page footer', () => {
    render(<ContractList />)
    expect(screen.getByTestId('page-footer')).toBeInTheDocument()
  })

  it('shows loading state', () => {
    mockUsePaginatedList.mockReturnValue({
      data: { items: [], total: 0 },
      isLoading: true,
      page: 1,
      setPage: vi.fn(),
      withPageReset: (fn: any) => fn,
    })
    render(<ContractList />)
    expect(screen.getByText('loading')).toBeInTheDocument()
  })

  it('passes contracts to table', () => {
    const contracts = [{ id: 1, name: '合同1' }, { id: 2, name: '合同2' }]
    mockUsePaginatedList.mockReturnValue({
      data: { items: contracts, total: 2 },
      isLoading: false,
      page: 1,
      setPage: vi.fn(),
      withPageReset: (fn: any) => fn,
    })
    render(<ContractList />)
    expect(screen.getByText('2 contracts')).toBeInTheDocument()
  })

  it('shows footer stats', () => {
    mockUsePaginatedList.mockReturnValue({
      data: { items: [], total: 5 },
      isLoading: false,
      page: 1,
      setPage: vi.fn(),
      withPageReset: (fn: any) => fn,
    })
    render(<ContractList />)
    expect(screen.getByText('5 条')).toBeInTheDocument()
  })
})
