vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  generatePath: { caseDetail: (id: string) => `/cases/${id}` },
}))

vi.mock('@/lib/date', () => ({
  formatDateOnly: (v: string | null) => v ?? '-',
}))

import { render, screen } from '@testing-library/react'
import { CaseTable } from '../CaseTable'

describe('CaseTable', () => {
  const mockCases = [
    {
      id: 1,
      name: '测试案件A',
      status: 'active',
      case_type: 'litigation',
      current_stage: 'filing',
      is_filed: true,
      filing_number: '(2026)京0101民初123号',
      start_date: '2026-01-01',
      assignments: [
        { id: 1, lawyer_detail: { real_name: '张三', username: 'zhang' } },
      ],
    },
    {
      id: 2,
      name: '测试案件B',
      status: 'closed',
      case_type: 'non_litigation',
      current_stage: null,
      is_filed: false,
      filing_number: null,
      start_date: null,
      assignments: [],
    },
  ]

  it('renders table headers', () => {
    render(<CaseTable cases={[]} isLoading={false} />)
    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('案件名称')).toBeInTheDocument()
    expect(screen.getByText('立案号')).toBeInTheDocument()
    expect(screen.getByText('案件类型')).toBeInTheDocument()
    expect(screen.getByText('状态')).toBeInTheDocument()
    expect(screen.getByText('律师')).toBeInTheDocument()
    expect(screen.getByText('当前阶段')).toBeInTheDocument()
    expect(screen.getByText('立案日期')).toBeInTheDocument()
  })

  it('renders case data', () => {
    render(<CaseTable cases={mockCases as any} isLoading={false} />)
    expect(screen.getByText('测试案件A')).toBeInTheDocument()
    expect(screen.getByText('测试案件B')).toBeInTheDocument()
    expect(screen.getByText('(2026)京0101民初123号')).toBeInTheDocument()
  })

  it('shows empty state when no cases', () => {
    render(<CaseTable cases={[]} isLoading={false} />)
    expect(screen.getByText('暂无案件数据')).toBeInTheDocument()
  })

  it('renders skeleton when loading', () => {
    const { container } = render(<CaseTable cases={[]} isLoading={true} />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('shows filed badge for filed cases', () => {
    render(<CaseTable cases={mockCases as any} isLoading={false} />)
    expect(screen.getByText('已建档')).toBeInTheDocument()
  })

  it('shows lawyer name from assignments', () => {
    render(<CaseTable cases={mockCases as any} isLoading={false} />)
    expect(screen.getByText('张三')).toBeInTheDocument()
  })

  it('shows dash when no assignments', () => {
    render(<CaseTable cases={mockCases as any} isLoading={false} />)
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThan(0)
  })

  it('shows multiple lawyers display', () => {
    const caseWithMultiple = [{
      ...mockCases[0],
      assignments: [
        { id: 1, lawyer_detail: { real_name: '张三', username: 'zhang' } },
        { id: 2, lawyer_detail: { real_name: '李四', username: 'li' } },
      ],
    }]
    render(<CaseTable cases={caseWithMultiple as any} isLoading={false} />)
    expect(screen.getByText('张三 等2人')).toBeInTheDocument()
  })
})
