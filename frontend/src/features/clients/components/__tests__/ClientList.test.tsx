vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))

vi.mock('@/components/shared/PageFooter', () => ({
  PageFooter: ({ stats, page, total, pageSize }: { stats: { label: string; value: string }[]; page: number; total: number; pageSize: number }) => (
    <div data-testid="page-footer">
      <span data-testid="total">{total}</span>
      <span data-testid="page">{page}</span>
      <span data-testid="pageSize">{pageSize}</span>
    </div>
  ),
}))

vi.mock('../ClientFilters', () => ({
  ClientFilters: (props: Record<string, unknown>) => (
    <div data-testid="client-filters">
      <input
        data-testid="search-input"
        value={props.search as string}
        onChange={(e) => (props.onSearchChange as (v: string) => void)(e.target.value)}
      />
    </div>
  ),
}))

vi.mock('../ClientTable', () => ({
  ClientTable: ({ clients, isLoading }: { clients: unknown[]; isLoading: boolean }) => (
    <div data-testid="client-table">
      {isLoading ? 'loading' : `${clients.length} clients`}
    </div>
  ),
}))

vi.mock('../api', () => ({
  clientApi: {
    list: vi.fn().mockResolvedValue([]),
  },
}))

vi.mock('@/hooks/use-paginated-list', () => ({
  usePaginatedList: vi.fn(() => ({
    data: { items: [], total: 0, page: 1, pageSize: 20, totalPages: 0 },
    isLoading: false,
    page: 1,
    setPage: vi.fn(),
    withPageReset: vi.fn((setter: unknown) => (v: unknown) => (setter as (v: unknown) => void)(v)),
  })),
}))

vi.mock('lucide-react', () => ({
  Plus: (p: Record<string, unknown>) => <svg data-testid="plus-icon" {...p} />,
}))

import { render, screen } from '@testing-library/react'
import { ClientList } from '../ClientList'
import { usePaginatedList } from '@/hooks/use-paginated-list'

describe('ClientList', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders the client table and filters', () => {
    render(<ClientList />)
    expect(screen.getByTestId('client-table')).toBeInTheDocument()
    expect(screen.getByTestId('client-filters')).toBeInTheDocument()
  })

  it('renders create button', () => {
    render(<ClientList />)
    expect(screen.getByText('新建当事人')).toBeInTheDocument()
  })

  it('shows loading state from usePaginatedList', () => {
    vi.mocked(usePaginatedList).mockReturnValue({
      data: { items: [], total: 0, page: 1, pageSize: 20, totalPages: 0 },
      isLoading: true,
      page: 1,
      setPage: vi.fn(),
      withPageReset: vi.fn((setter: unknown) => (v: unknown) => (setter as (v: unknown) => void)(v)),
    } as ReturnType<typeof usePaginatedList>)

    render(<ClientList />)
    expect(screen.getByTestId('client-table')).toHaveTextContent('loading')
  })

  it('shows paginated data when loaded', () => {
    vi.mocked(usePaginatedList).mockReturnValue({
      data: {
        items: [
          { id: 1, name: 'Wang' },
          { id: 2, name: 'Li' },
        ],
        total: 2,
        page: 1,
        pageSize: 20,
        totalPages: 1,
      },
      isLoading: false,
      page: 1,
      setPage: vi.fn(),
      withPageReset: vi.fn((setter: unknown) => (v: unknown) => (setter as (v: unknown) => void)(v)),
    } as ReturnType<typeof usePaginatedList>)

    render(<ClientList />)
    expect(screen.getByTestId('client-table')).toHaveTextContent('2 clients')
  })

  it('renders page footer with total count', () => {
    vi.mocked(usePaginatedList).mockReturnValue({
      data: { items: [], total: 42, page: 1, pageSize: 20, totalPages: 3 },
      isLoading: false,
      page: 1,
      setPage: vi.fn(),
      withPageReset: vi.fn((setter: unknown) => (v: unknown) => (setter as (v: unknown) => void)(v)),
    } as ReturnType<typeof usePaginatedList>)

    render(<ClientList />)
    expect(screen.getByTestId('page-footer')).toBeInTheDocument()
    expect(screen.getByTestId('total')).toHaveTextContent('42')
  })
})
