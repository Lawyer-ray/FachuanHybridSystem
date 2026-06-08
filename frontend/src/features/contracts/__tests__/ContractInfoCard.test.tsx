import { render, screen } from '@testing-library/react'
import { ContractInfoCard } from '../components/ContractInfoCard'

vi.mock('lucide-react', () => ({
  Calendar: () => <svg data-testid="calendar" />,
  Scale: () => <svg data-testid="scale" />,
  User: () => <svg data-testid="user" />,
  Users: () => <svg data-testid="users" />,
  Briefcase: () => <svg data-testid="briefcase" />,
  FileText: () => <svg data-testid="file-text" />,
  DollarSign: () => <svg data-testid="dollar" />,
  Tag: () => <svg data-testid="tag" />,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))

vi.mock('@/components/ui/separator', () => ({
  Separator: () => <hr data-testid="separator" />,
}))

vi.mock('@/lib/format', () => ({
  formatAmountInt: (val: number) => `¥${val.toLocaleString()}`,
}))

const mockContract = {
  id: 1,
  name: '委托代理合同',
  case_type_label: '民事',
  status: 'active',
  status_label: '进行中',
  is_filed: true,
  specified_date: '2024-01-15',
  start_date: '2024-01-01',
  end_date: '2024-12-31',
  representation_stages: ['一审', '二审'],
  fee_mode: 'fixed',
  fixed_amount: 50000,
  risk_rate: null,
  custom_terms: null,
  total_received: 30000,
  total_invoiced: 20000,
  unpaid_amount: 20000,
  assignments: [
    { id: 1, lawyer_name: '张律师', is_primary: true },
    { id: 2, lawyer_name: '李律师', is_primary: false },
  ],
  contract_parties: [
    { id: 1, client_detail: { name: '王客户' }, role_label: '委托方' },
  ],
  cases: [
    { id: 1, name: '合同纠纷案', status_label: '进行中', target_amount: 100000 },
  ],
}

describe('ContractInfoCard', () => {
  it('renders contract name', () => {
    render(<ContractInfoCard contract={mockContract as never} />)
    expect(screen.getByText('委托代理合同')).toBeInTheDocument()
  })

  it('renders case type badge', () => {
    render(<ContractInfoCard contract={mockContract as never} />)
    expect(screen.getByText('民事')).toBeInTheDocument()
  })

  it('renders representation stages', () => {
    render(<ContractInfoCard contract={mockContract as never} />)
    expect(screen.getByText('一审')).toBeInTheDocument()
    expect(screen.getByText('二审')).toBeInTheDocument()
  })

  it('renders assignment lawyers', () => {
    render(<ContractInfoCard contract={mockContract as never} />)
    expect(screen.getByText('张律师')).toBeInTheDocument()
    expect(screen.getByText('李律师')).toBeInTheDocument()
    expect(screen.getByText('主办')).toBeInTheDocument()
  })

  it('renders contract parties', () => {
    render(<ContractInfoCard contract={mockContract as never} />)
    expect(screen.getByText('王客户')).toBeInTheDocument()
    expect(screen.getByText('委托方')).toBeInTheDocument()
  })

  it('renders related cases', () => {
    render(<ContractInfoCard contract={mockContract as never} />)
    expect(screen.getByText('合同纠纷案')).toBeInTheDocument()
  })

  it('renders empty states when no assignments/parties', () => {
    const emptyContract = { ...mockContract, assignments: [], contract_parties: [], cases: [] }
    render(<ContractInfoCard contract={emptyContract as never} />)
    expect(screen.getByText('未指派')).toBeInTheDocument()
    expect(screen.getByText('未添加')).toBeInTheDocument()
  })

  it('renders filed badge', () => {
    render(<ContractInfoCard contract={mockContract as never} />)
    expect(screen.getByText('已建档')).toBeInTheDocument()
  })
})
