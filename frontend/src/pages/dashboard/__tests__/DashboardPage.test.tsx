import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import DashboardPage from '../DashboardPage'

// Mock dashboard feature
vi.mock('@/features/dashboard', () => ({
  useDashboardStats: vi.fn().mockReturnValue({
    data: null,
    isLoading: true,
  }),
}))

vi.mock('@/features/dashboard/components/StatsCards', () => ({
  StatsCards: ({ isLoading }: { isLoading: boolean }) => (
    <div data-testid="stats-cards">{isLoading ? 'Loading' : 'Loaded'}</div>
  ),
}))

vi.mock('@/features/dashboard/components/TrendChart', () => ({
  TrendChart: () => <div data-testid="trend-chart" />,
}))

vi.mock('@/features/dashboard/components/CaseDistributionChart', () => ({
  CaseDistributionChart: () => <div data-testid="case-distribution-chart" />,
}))

vi.mock('@/features/dashboard/components/CalendarCard', () => ({
  CalendarCard: () => <div data-testid="calendar-card" />,
}))

describe('DashboardPage', () => {
  it('renders the page title', () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('仪表盘')).toBeInTheDocument()
  })

  it('renders welcome message', () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('欢迎回来。以下是今日概览。')).toBeInTheDocument()
  })

  it('renders stats cards', () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('stats-cards')).toBeInTheDocument()
  })

  it('renders trend chart', () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('trend-chart')).toBeInTheDocument()
  })

  it('renders case distribution chart', () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('case-distribution-chart')).toBeInTheDocument()
  })

  it('renders calendar card', () => {
    render(
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('calendar-card')).toBeInTheDocument()
  })
})
