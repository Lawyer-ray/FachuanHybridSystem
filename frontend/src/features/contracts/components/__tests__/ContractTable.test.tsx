vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  generatePath: { contractDetail: (id: number) => `/contracts/${id}` },
}))

vi.mock('@/lib/format', () => ({
  formatAmountInt: (v: number | null) => (v != null ? `¥${v}` : '-'),
}))

import { render, screen } from '@testing-library/react'
import { ContractTable } from '../ContractTable'

describe('ContractTable', () => {
  const mockContracts = [
    {
      id: 1, name: '民商事合同A', case_type_label: '民事', status: 'active', status_label: '执行中',
      fee_mode: 'fixed', start_date: '2026-01-01', total_received: 50000, is_filed: true,
      primary_lawyer: { real_name: '张三', username: 'zhang' },
    },
  ]

  it('renders table headers', () => {
    render(<ContractTable contracts={[]} />)
    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('类型')).toBeInTheDocument()
    expect(screen.getByText('合同名称')).toBeInTheDocument()
    expect(screen.getByText('状态')).toBeInTheDocument()
  })

  it('renders contract data', () => {
    render(<ContractTable contracts={mockContracts as any} />)
    expect(screen.getByText('民商事合同A')).toBeInTheDocument()
    expect(screen.getByText('民事')).toBeInTheDocument()
    expect(screen.getByText('张三')).toBeInTheDocument()
  })

  it('shows empty state when no contracts', () => {
    render(<ContractTable contracts={[]} />)
    expect(screen.getByText('暂无合同数据')).toBeInTheDocument()
  })

  it('shows filed badge', () => {
    render(<ContractTable contracts={mockContracts as any} />)
    expect(screen.getByText('已建档')).toBeInTheDocument()
  })
})
