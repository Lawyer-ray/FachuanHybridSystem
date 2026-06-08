import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { TrendChart } from '../TrendChart'

vi.mock('recharts', () => ({
  AreaChart: ({ children }: React.PropsWithChildren) => <div data-testid="area-chart">{children}</div>,
  Area: () => <div data-testid="area" />,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}))

describe('TrendChart', () => {
  it('renders skeleton when loading', () => {
    const { container } = render(<TrendChart isLoading data={undefined} />)
    expect(container.querySelector('[class*="animate-pulse"]')).toBeInTheDocument()
  })

  it('renders empty state when no trend data', () => {
    render(
      <TrendChart
        isLoading={false}
        data={{ case_trend: [], contract_trend: [], fee_trend: [] } as any}
      />,
    )
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
  })

  it('renders chart title', () => {
    render(<TrendChart isLoading={false} data={undefined} />)
    expect(screen.getByText('趋势')).toBeInTheDocument()
  })

  it('renders tab buttons for case, contract, fee', () => {
    render(<TrendChart isLoading={false} data={undefined} />)
    expect(screen.getByRole('tab', { name: '案件' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '合同' })).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: '收入' })).toBeInTheDocument()
  })

  it('renders the chart when trend data exists', () => {
    const data = {
      case_trend: [{ month: '1月', count: 5 }],
      contract_trend: [],
      fee_trend: [],
    }
    render(<TrendChart isLoading={false} data={data as any} />)
    expect(screen.getByTestId('area-chart')).toBeInTheDocument()
  })

  it('switches tabs', async () => {
    const data = {
      case_trend: [{ month: '1月', count: 5 }],
      contract_trend: [{ month: '1月', count: 3 }],
      fee_trend: [],
    }
    const user = userEvent.setup()
    render(<TrendChart isLoading={false} data={data as any} />)

    await user.click(screen.getByRole('tab', { name: '合同' }))
    expect(screen.getByRole('tab', { name: '合同' })).toHaveAttribute('data-state', 'active')
  })
})
