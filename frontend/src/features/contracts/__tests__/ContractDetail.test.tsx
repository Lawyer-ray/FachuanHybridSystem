import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { ContractDetail } from '../components/ContractDetail'
import type { Contract } from '../types'

// ── Mocks ──

vi.mock('lucide-react', () => ({
  ArrowLeft: (p: Record<string, unknown>) => <svg data-testid="arrow-left" {...p} />,
  Edit: (p: Record<string, unknown>) => <svg data-testid="edit" {...p} />,
  Trash2: (p: Record<string, unknown>) => <svg data-testid="trash" {...p} />,
  FileWarning: (p: Record<string, unknown>) => <svg data-testid="file-warning" {...p} />,
  MoreHorizontal: (p: Record<string, unknown>) => <svg data-testid="more" {...p} />,
  FileText: (p: Record<string, unknown>) => <svg data-testid="file-text" {...p} />,
  Briefcase: (p: Record<string, unknown>) => <svg data-testid="briefcase" {...p} />,
  Copy: (p: Record<string, unknown>) => <svg data-testid="copy" {...p} />,
  RefreshCw: (p: Record<string, unknown>) => <svg data-testid="refresh" {...p} />,
  Loader2: (p: Record<string, unknown>) => <svg data-testid="loader" {...p} />,
  User: (p: Record<string, unknown>) => <svg data-testid="user" {...p} />,
  Scale: (p: Record<string, unknown>) => <svg data-testid="scale" {...p} />,
  ChevronDown: (p: Record<string, unknown>) => <svg data-testid="chevron-down" {...p} />,
  ChevronRight: (p: Record<string, unknown>) => <svg data-testid="chevron-right" {...p} />,
  Users: (p: Record<string, unknown>) => <svg data-testid="users" {...p} />,
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('react-router', () => ({
  useNavigate: () => vi.fn(),
}))

vi.mock('framer-motion', () => ({
  AnimatePresence: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  motion: {
    div: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  },
}))

vi.mock('@/lib/clipboard', () => ({
  copyToClipboard: vi.fn(),
}))

vi.mock('@/lib/format', () => ({
  formatAmount: (v: number) => `¥${v.toLocaleString()}`,
  formatAmountInt: (v: number) => `¥${v.toLocaleString()}`,
}))

vi.mock('@/lib/download', () => ({
  downloadBlob: vi.fn(),
}))

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_CONTRACTS: '/admin/contracts' },
  generatePath: {
    contractEdit: (id: string) => `/admin/contracts/${id}/edit`,
    contractDetail: (id: number) => `/admin/contracts/${id}`,
  },
}))

let mockContractData: Contract | undefined = makeContract()
let mockIsLoading = false
let mockError: Error | null = null

vi.mock('../hooks/use-contract', () => ({
  useContract: () => ({ data: mockContractData, isLoading: mockIsLoading, error: mockError }),
}))

vi.mock('../hooks/use-contract-mutations', () => ({
  useContractMutations: () => ({
    deleteContract: { mutateAsync: vi.fn().mockResolvedValue(undefined) },
    duplicateContract: { mutateAsync: vi.fn().mockResolvedValue({ id: 999 }) },
    createCaseFromContract: { mutateAsync: vi.fn().mockResolvedValue({ message: 'ok' }) },
  }),
}))

vi.mock('../api', () => ({
  contractApi: {
    generateContract: vi.fn(),
  },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, ...props }: Record<string, unknown>) => <span {...props}>{children}</span>,
}))

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) =>
    open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogAction: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/sheet', () => ({
  Sheet: ({ children, open }: { children: React.ReactNode; open?: boolean }) =>
    open ? <div data-testid="sheet">{children}</div> : null,
  SheetContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/shared', () => ({
  DetailField: ({ label, value }: { label: string; value: unknown }) => (
    <div data-testid={`field-${label}`}>
      <span>{label}</span>
      {value != null && typeof value !== 'object' ? <span>{String(value)}</span> : value as React.ReactNode}
    </div>
  ),
  DetailCard: ({ title, children, extra }: { title: string; children: React.ReactNode; extra?: React.ReactNode }) => (
    <div data-testid={`card-${title}`}>
      <div>{title}</div>
      {extra}
      {children}
    </div>
  ),
  StatusBadge: ({ children, variant }: { children: React.ReactNode; variant?: string }) => (
    <span data-testid="status-badge" data-variant={variant}>{children}</span>
  ),
}))

vi.mock('../components/SupplementaryAgreementList', () => ({
  SupplementaryAgreementList: () => <div data-testid="agreement-list" />,
}))

vi.mock('../components/FeesTab', () => ({
  FeesTab: () => <div data-testid="fees-tab" />,
}))

vi.mock('../components/FilingTab', () => ({
  FilingTab: () => <div data-testid="filing-tab" />,
}))

vi.mock('../components/DocumentsTab', () => ({
  DocumentsTab: () => <div data-testid="documents-tab" />,
}))

vi.mock('../components/ArchiveTab', () => ({
  ArchiveTab: () => <div data-testid="archive-tab" />,
}))

// ── Helpers ──

function makeContract(overrides: Partial<Contract> = {}): Contract {
  return {
    id: 1,
    name: 'Test Contract',
    case_type: 'civil',
    status: 'active',
    specified_date: '2024-01-01',
    start_date: '2024-01-01',
    end_date: '2024-12-31',
    is_filed: true,
    fee_mode: 'FIXED',
    fixed_amount: 100000,
    risk_rate: 10,
    custom_terms: null,
    representation_stages: ['一审'],
    cases: [{ id: 1, name: 'Case A', cause_of_action: '纠纷', status_label: '进行中', target_amount: 50000 } as never],
    contract_parties: [
      {
        id: 1,
        client: 1,
        role: 'PRINCIPAL',
        role_label: '委托方',
        client_detail: {
          id: 1,
          name: 'Client A',
          is_our_client: true,
          phone: '123456',
          address: 'Addr',
          client_type: 'natural',
          id_number: 'ID123',
          legal_representative: null,
          legal_representative_id_number: null,
          client_type_label: '自然人',
          identity_docs: [],
        },
      },
    ],
    assignments: [
      { id: 1, lawyer_id: 1, lawyer_name: '张律师', is_primary: true, order: 0 },
    ],
    supplementary_agreements: [],
    payments: [],
    client_payment_records: [],
    reminders: [],
    total_received: 50000,
    total_invoiced: 30000,
    unpaid_amount: 50000,
    ...overrides,
  } as Contract
}

// ── Tests ──

describe('ContractDetail', () => {
  beforeEach(() => {
    mockContractData = makeContract()
    mockIsLoading = false
    mockError = null
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('shows loading skeleton when loading', () => {
    mockIsLoading = true
    mockContractData = undefined
    render(<ContractDetail contractId="1" />)
    expect(screen.queryByText('Test Contract')).not.toBeInTheDocument()
  })

  it('shows error state when contract not found', () => {
    mockContractData = undefined
    mockError = new Error('not found')
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('合同不存在')).toBeInTheDocument()
  })

  it('shows error state when contract is null', () => {
    mockContractData = undefined
    mockError = null
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('合同不存在')).toBeInTheDocument()
  })

  it('renders contract name', () => {
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('Test Contract').length).toBeGreaterThan(0)
  })

  it('renders status badge with label', () => {
    render(<ContractDetail contractId="1" />)
    const badges = screen.getAllByTestId('status-badge')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('renders filed indicator', () => {
    render(<ContractDetail contractId="1" />)
    const filedElements = screen.getAllByText('已建档')
    expect(filedElements.length).toBeGreaterThan(0)
  })

  it('renders unfilled indicator', () => {
    mockContractData = makeContract({ is_filed: false })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('未建档')).toBeInTheDocument()
  })

  it('renders primary lawyer name', () => {
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('张律师')).toBeInTheDocument()
  })

  it('renders "未指派" when no primary lawyer', () => {
    mockContractData = makeContract({ assignments: [] })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('未指派')).toBeInTheDocument()
  })

  it('renders tabs', () => {
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('基本信息')).toBeInTheDocument()
    expect(screen.getByText('当事人与律师')).toBeInTheDocument()
    expect(screen.getByText('收费与财务')).toBeInTheDocument()
    expect(screen.getByText('立案')).toBeInTheDocument()
    expect(screen.getByText('文档与提醒')).toBeInTheDocument()
    expect(screen.getByText('归档')).toBeInTheDocument()
  })

  it('switches to parties tab', () => {
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    expect(screen.getByText('合同当事人')).toBeInTheDocument()
    expect(screen.getByText('律师指派')).toBeInTheDocument()
  })

  it('shows parties with no data', () => {
    mockContractData = makeContract({ contract_parties: [], assignments: [], supplementary_agreements: [] })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    expect(screen.getByText('暂无当事人')).toBeInTheDocument()
    expect(screen.getByText('暂无指派律师')).toBeInTheDocument()
  })

  it('clicking party opens sheet', () => {
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('Client A'))
    expect(screen.getByTestId('sheet')).toBeInTheDocument()
  })

  it('clicking lawyer opens sheet', () => {
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    const lawyers = screen.getAllByText('张律师')
    // Click the one in the lawyer list (not the header)
    fireEvent.click(lawyers[lawyers.length - 1])
    expect(screen.getByTestId('sheet')).toBeInTheDocument()
  })

  it('renders supplementary agreements when present', () => {
    mockContractData = makeContract({ supplementary_agreements: [{ id: 1 } as never] })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    expect(screen.getByTestId('agreement-list')).toBeInTheDocument()
  })

  it('switches to fees tab', () => {
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('收费与财务'))
    expect(screen.getByTestId('fees-tab')).toBeInTheDocument()
  })

  it('switches to filing tab', () => {
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('立案'))
    expect(screen.getByTestId('filing-tab')).toBeInTheDocument()
  })

  it('switches to documents tab', () => {
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('文档与提醒'))
    expect(screen.getByTestId('documents-tab')).toBeInTheDocument()
  })

  it('switches to archive tab', () => {
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('归档'))
    expect(screen.getByTestId('archive-tab')).toBeInTheDocument()
  })

  it('renders basic tab content with risk rate', () => {
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('10%')).toBeInTheDocument()
  })

  it('renders risk rate dash when null', () => {
    mockContractData = makeContract({ risk_rate: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('—')).toBeInTheDocument()
  })

  it('renders related cases', () => {
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('Case A')).toBeInTheDocument()
  })

  it('hides related cases when empty', () => {
    mockContractData = makeContract({ cases: [] })
    render(<ContractDetail contractId="1" />)
    expect(screen.queryByText('关联案件')).not.toBeInTheDocument()
  })

  it('renders advisor contract renew option', () => {
    mockContractData = makeContract({ case_type: 'advisor' })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('续签顾问合同')).toBeInTheDocument()
  })

  it('hides renew option for non-advisor contract', () => {
    render(<ContractDetail contractId="1" />)
    expect(screen.queryByText('续签顾问合同')).not.toBeInTheDocument()
  })

  it('opens delete dialog', () => {
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('删除'))
    expect(screen.getByText('确认删除合同')).toBeInTheDocument()
  })

  it('renders contract with null start/end dates', () => {
    mockContractData = makeContract({ start_date: null, end_date: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText(/— ~ —/)).toBeInTheDocument()
  })

  it('renders non-natural client type in party sheet', () => {
    const party = {
      id: 1,
      client: 1,
      role: 'PRINCIPAL',
      role_label: '委托方',
      client_detail: {
        id: 1,
        name: 'Corp A',
        is_our_client: false,
        phone: '123',
        address: 'Addr',
        client_type: 'legal',
        id_number: 'SC123',
        legal_representative: 'John',
        legal_representative_id_number: 'ID789',
        client_type_label: '法人',
        identity_docs: [],
      },
    }
    mockContractData = makeContract({ contract_parties: [party as never] })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('Corp A'))
    expect(screen.getByText('法定代表人信息')).toBeInTheDocument()
  })

  it('renders representation stages joined', () => {
    mockContractData = makeContract({ representation_stages: ['一审', '二审'] })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('一审、二审')).toBeInTheDocument()
  })

  it('renders dash when no representation stages', () => {
    mockContractData = makeContract({ representation_stages: [] })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('代理阶段')).toBeInTheDocument()
  })

  it('renders case with cause_of_action', () => {
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('纠纷')).toBeInTheDocument()
  })

  it('renders case without cause_of_action', () => {
    mockContractData = makeContract({ cases: [{ id: 1, name: 'Case B', cause_of_action: null, status_label: null, target_amount: null } as never] })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('Case B')).toBeInTheDocument()
  })

  it('renders custom terms when set', () => {
    mockContractData = makeContract({ custom_terms: 'Custom terms' })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('Custom terms')).toBeInTheDocument()
  })

  it('handles unknown status falls back to raw value', () => {
    mockContractData = makeContract({ status: 'unknown' as never })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('unknown').length).toBeGreaterThan(0)
  })
})
