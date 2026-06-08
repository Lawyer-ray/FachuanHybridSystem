import { render, screen } from '@testing-library/react'
import { CaseDistributionChart } from '../CaseDistributionChart'

vi.mock('recharts', () => ({
  PieChart: ({ children }: React.PropsWithChildren) => <div data-testid="pie-chart">{children}</div>,
  Pie: () => <div data-testid="pie" />,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  Legend: () => null,
}))

describe('CaseDistributionChart', () => {
  it('renders skeleton when loading', () => {
    const { container } = render(<CaseDistributionChart isLoading data={undefined} />)
    expect(container.querySelector('[class*="animate-pulse"]')).toBeInTheDocument()
  })

  it('renders empty state when no data', () => {
    render(<CaseDistributionChart isLoading={false} data={{ case_type_distribution: [] } as any} />)
    expect(screen.getByText('暂无数据')).toBeInTheDocument()
  })

  it('renders chart title', () => {
    render(<CaseDistributionChart isLoading={false} data={undefined} />)
    expect(screen.getByText('案件类型分布')).toBeInTheDocument()
  })

  it('renders the chart when data is available', () => {
    const data = {
      case_type_distribution: [
        { label: '诉讼', count: 5 },
        { label: '非诉', count: 3 },
      ],
    }
    render(<CaseDistributionChart isLoading={false} data={data as any} />)
    expect(screen.getByTestId('pie-chart')).toBeInTheDocument()
  })

  it('shows total count in chart center', () => {
    const data = {
      case_type_distribution: [
        { label: '诉讼', count: 5 },
        { label: '非诉', count: 3 },
      ],
    }
    render(<CaseDistributionChart isLoading={false} data={data as any} />)
    expect(screen.getByText('8')).toBeInTheDocument()
    expect(screen.getByText('在办案件')).toBeInTheDocument()
  })
})
