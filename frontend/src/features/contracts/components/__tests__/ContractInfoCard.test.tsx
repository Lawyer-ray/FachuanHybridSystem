import { render, screen } from '@testing-library/react'
import { ContractInfoCard } from '../components/ContractInfoCard'
import type { Contract } from '../types'

// ── Mocks ──

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

// ── Helpers ──

function makeContract(overrides: Partial<Contract> = {}): Contract {
  return {
    id: 1,
    name: 'Test Contract',
    case_type_label: '民事',
    status: 'active',
    status_label: '进行中',
    is_filed: true,
    specified_date: '2024-01-15',
    start_date: '2024-01-01',
    end_date: '2024-12-31',
    representation_stages: ['一审', '二审'],
    fee_mode: 'FIXED',
    fixed_amount: 50000,
    risk_rate: null,
    custom_terms: null,
    total_received: 30000,
    total_invoiced: 20000,
    unpaid_amount: 20000,
    assignments: [
      { id: 1, lawyer_name: '张律师', is_primary: true, lawyer_id: 1, order: 0 },
    ],
    contract_parties: [
      { id: 1, client_detail: { name: '王客户' }, role_label: '委托方' } as never,
    ],
    cases: [
      { id: 1, name: '合同纠纷案', status_label: '进行中', target_amount: 100000 } as never,
    ],
    ...overrides,
  } as Contract
}

// ── Tests ──

describe('ContractInfoCard', () => {
  it('renders contract name', () => {
    render(<ContractInfoCard contract={makeContract()} />)
    expect(screen.getByText('Test Contract')).toBeInTheDocument()
  })

  it('renders case type badge', () => {
    render(<ContractInfoCard contract={makeContract()} />)
    expect(screen.getByText('民事')).toBeInTheDocument()
  })

  it('renders active status with default variant', () => {
    render(<ContractInfoCard contract={makeContract({ status: 'active' })} />)
    const badges = screen.getAllByText('进行中')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('renders archived status with secondary variant', () => {
    render(<ContractInfoCard contract={makeContract({ status: 'archived' })} />)
    const badges = screen.getAllByText('进行中')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('renders closed status with outline variant', () => {
    render(<ContractInfoCard contract={makeContract({ status: 'closed' })} />)
    const badges = screen.getAllByText('进行中')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('renders non-filed contract without filed badge', () => {
    render(<ContractInfoCard contract={makeContract({ is_filed: false })} />)
    expect(screen.queryByText('已建档')).not.toBeInTheDocument()
  })

  it('renders filed badge', () => {
    render(<ContractInfoCard contract={makeContract({ is_filed: true })} />)
    expect(screen.getByText('已建档')).toBeInTheDocument()
  })

  it('renders fallback date when specified_date is null', () => {
    render(<ContractInfoCard contract={makeContract({ specified_date: null })} />)
    expect(screen.getByText('-')).toBeInTheDocument()
  })

  it('renders fallback dates when start/end dates are null', () => {
    render(<ContractInfoCard contract={makeContract({ start_date: null, end_date: null })} />)
    expect(screen.getByText('- ~ -')).toBeInTheDocument()
  })

  it('hides representation stages when empty', () => {
    render(<ContractInfoCard contract={makeContract({ representation_stages: [] })} />)
    expect(screen.queryByText('代理阶段')).not.toBeInTheDocument()
  })

  it('renders representation stages', () => {
    render(<ContractInfoCard contract={makeContract()} />)
    expect(screen.getByText('一审')).toBeInTheDocument()
    expect(screen.getByText('二审')).toBeInTheDocument()
  })

  it('renders fixed amount', () => {
    render(<ContractInfoCard contract={makeContract()} />)
    expect(screen.getByText('¥50,000')).toBeInTheDocument()
  })

  it('hides fixed amount when null', () => {
    render(<ContractInfoCard contract={makeContract({ fixed_amount: null })} />)
    expect(screen.queryByText('固定/前期金额')).not.toBeInTheDocument()
  })

  it('renders risk rate', () => {
    render(<ContractInfoCard contract={makeContract({ risk_rate: 15 })} />)
    expect(screen.getByText('15%')).toBeInTheDocument()
  })

  it('hides risk rate when null', () => {
    render(<ContractInfoCard contract={makeContract({ risk_rate: null })} />)
    expect(screen.queryByText('风险比例')).not.toBeInTheDocument()
  })

  it('renders custom terms', () => {
    render(<ContractInfoCard contract={makeContract({ custom_terms: 'Custom terms here' })} />)
    expect(screen.getByText('Custom terms here')).toBeInTheDocument()
  })

  it('hides custom terms when null', () => {
    render(<ContractInfoCard contract={makeContract({ custom_terms: null })} />)
    expect(screen.queryByText('自定义条款')).not.toBeInTheDocument()
  })

  it('renders unpaid amount when not null', () => {
    render(<ContractInfoCard contract={makeContract({ unpaid_amount: 10000 })} />)
    expect(screen.getByText('未收款')).toBeInTheDocument()
  })

  it('hides unpaid amount when null', () => {
    render(<ContractInfoCard contract={makeContract({ unpaid_amount: null })} />)
    expect(screen.queryByText('未收款')).not.toBeInTheDocument()
  })

  it('renders assignment lawyers with primary badge', () => {
    render(<ContractInfoCard contract={makeContract()} />)
    expect(screen.getByText('张律师')).toBeInTheDocument()
    expect(screen.getByText('主办')).toBeInTheDocument()
  })

  it('renders assignment without primary badge', () => {
    const contract = makeContract({
      assignments: [{ id: 2, lawyer_name: '李律师', is_primary: false, lawyer_id: 2, order: 0 }],
    })
    render(<ContractInfoCard contract={contract} />)
    expect(screen.getByText('李律师')).toBeInTheDocument()
  })

  it('renders empty assignments', () => {
    render(<ContractInfoCard contract={makeContract({ assignments: [] })} />)
    expect(screen.getByText('未指派')).toBeInTheDocument()
  })

  it('renders contract parties', () => {
    render(<ContractInfoCard contract={makeContract()} />)
    expect(screen.getByText('王客户')).toBeInTheDocument()
    expect(screen.getByText('委托方')).toBeInTheDocument()
  })

  it('renders empty parties', () => {
    render(<ContractInfoCard contract={makeContract({ contract_parties: [] })} />)
    expect(screen.getByText('未添加')).toBeInTheDocument()
  })

  it('renders related cases with target_amount', () => {
    render(<ContractInfoCard contract={makeContract()} />)
    expect(screen.getByText('合同纠纷案')).toBeInTheDocument()
  })

  it('renders related cases without target_amount', () => {
    const contract = makeContract({
      cases: [{ id: 1, name: 'Case A', status_label: null, target_amount: null } as never],
    })
    render(<ContractInfoCard contract={contract} />)
    expect(screen.getByText('Case A')).toBeInTheDocument()
  })

  it('hides cases card when no cases', () => {
    render(<ContractInfoCard contract={makeContract({ cases: [] })} />)
    expect(screen.queryByText('关联案件')).not.toBeInTheDocument()
  })

  it('renders case without status_label', () => {
    const contract = makeContract({
      cases: [{ id: 1, name: 'Case B', status_label: null, target_amount: 5000 } as never],
    })
    render(<ContractInfoCard contract={contract} />)
    expect(screen.getByText('Case B')).toBeInTheDocument()
  })

  it('renders with unknown fee_mode falls back to raw value', () => {
    render(<ContractInfoCard contract={makeContract({ fee_mode: 'UNKNOWN' })} />)
    expect(screen.getByText('UNKNOWN')).toBeInTheDocument()
  })
})
