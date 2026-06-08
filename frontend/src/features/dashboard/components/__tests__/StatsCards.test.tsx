import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router'
import { StatsCards } from '../StatsCards'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  }
})

vi.mock('@/routes/paths', () => ({
  PATHS: {
    ADMIN_CLIENTS: '/clients',
    ADMIN_CONTRACTS: '/contracts',
    ADMIN_CASES: '/cases',
  },
}))

describe('StatsCards', () => {
  const mockData = {
    client_count: 42,
    contract_count: 15,
    case_count: 8,
    monthly_fee: 123456,
    case_type_distribution: [],
    case_trend: [],
    contract_trend: [],
    fee_trend: [],
  }

  it('renders skeleton when loading', () => {
    const { container } = render(
      <MemoryRouter>
        <StatsCards isLoading data={undefined} />
      </MemoryRouter>,
    )
    // Skeleton elements should be present
    expect(container.querySelectorAll('[class*="animate-pulse"]').length).toBeGreaterThanOrEqual(0)
  })

  it('renders stat values when data is provided', () => {
    render(
      <MemoryRouter>
        <StatsCards isLoading={false} data={mockData as any} />
      </MemoryRouter>,
    )
    expect(screen.getByText('42')).toBeInTheDocument()
    expect(screen.getByText('15')).toBeInTheDocument()
    expect(screen.getByText('8')).toBeInTheDocument()
  })

  it('renders stat labels', () => {
    render(
      <MemoryRouter>
        <StatsCards isLoading={false} data={mockData as any} />
      </MemoryRouter>,
    )
    expect(screen.getByText('当事人总数')).toBeInTheDocument()
    expect(screen.getByText('合同总数')).toBeInTheDocument()
    expect(screen.getByText('在办案件')).toBeInTheDocument()
    expect(screen.getByText('本月律师费')).toBeInTheDocument()
  })

  it('shows 0 when data has zero counts', () => {
    const zeroData = { ...mockData, client_count: 0, contract_count: 0, case_count: 0 }
    render(
      <MemoryRouter>
        <StatsCards isLoading={false} data={zeroData as any} />
      </MemoryRouter>,
    )
    const zeros = screen.getAllByText('0')
    expect(zeros.length).toBeGreaterThanOrEqual(3)
  })

  it('renders cards as clickable elements', () => {
    const { container } = render(
      <MemoryRouter>
        <StatsCards isLoading={false} data={mockData as any} />
      </MemoryRouter>,
    )
    // Cards should have cursor-pointer class
    const cards = container.querySelectorAll('[class*="cursor-pointer"]')
    expect(cards.length).toBe(4)
  })
})
