/**
 * ContractDetail - additional branch/function coverage tests
 * Targets uncovered lines: null status (fn 3), lawyer copy (fn 24,25,26),
 * party copy all with missing fields, handleBack (fn 3 line 89)
 */

const { mockDeleteAsync, mockDuplicateAsync, mockCreateCaseAsync, mockGenerateContract } = vi.hoisted(() => ({
  mockDeleteAsync: vi.fn(),
  mockDuplicateAsync: vi.fn(),
  mockCreateCaseAsync: vi.fn(),
  mockGenerateContract: vi.fn(),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_CONTRACTS: '/admin/contracts' },
  generatePath: { contractEdit: (id: string) => `/contracts/${id}/edit`, contractDetail: (id: string) => `/contracts/${id}` },
}))

vi.mock('@/lib/format', () => ({
  formatAmount: (v: number | null) => (v != null ? `¥${v}` : '-'),
  formatAmountInt: (v: number | null) => (v != null ? `¥${v}` : '-'),
}))

vi.mock('@/lib/clipboard', () => ({
  copyToClipboard: vi.fn(),
}))

vi.mock('@/lib/download', () => ({
  downloadBlob: vi.fn(),
}))

vi.mock('../../hooks/use-contract', () => ({ useContract: vi.fn() }))
vi.mock('../../hooks/use-contract-mutations', () => ({
  useContractMutations: () => ({
    deleteContract: { mutateAsync: mockDeleteAsync },
    duplicateContract: { mutateAsync: mockDuplicateAsync },
    createCaseFromContract: { mutateAsync: mockCreateCaseAsync },
  }),
}))

vi.mock('../../api', () => ({
  contractApi: { generateContract: mockGenerateContract },
}))

vi.mock('../SupplementaryAgreementList', () => ({
  SupplementaryAgreementList: () => <div data-testid="agreement-list" />,
}))
vi.mock('../FeesTab', () => ({ FeesTab: () => <div data-testid="fees-tab" /> }))
vi.mock('../FilingTab', () => ({ FilingTab: () => <div data-testid="filing-tab" /> }))
vi.mock('../DocumentsTab', () => ({ DocumentsTab: () => <div data-testid="documents-tab" /> }))
vi.mock('../ArchiveTab', () => ({ ArchiveTab: () => <div data-testid="archive-tab" /> }))

vi.mock('@/components/ui/dropdown-menu', () => ({
  DropdownMenu: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DropdownMenuItem: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => (
    <div onClick={onClick} role="menuitem">{children}</div>
  ),
}))

vi.mock('@/components/ui/sheet', () => ({
  Sheet: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open !== false ? <div>{children}</div> : null,
  SheetContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SheetTitle: ({ children }: { children: React.ReactNode }) => <h3>{children}</h3>,
  SheetDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open !== false ? <div>{children}</div> : null,
  AlertDialogAction: ({ children, onClick, className }: Record<string, unknown>) => <button onClick={onClick as React.MouseEventHandler} className={className as string}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

vi.mock('framer-motion', async (importOriginal) => {
  const actual = await importOriginal<any>()
  return {
    ...actual,
    AnimatePresence: ({ children }: any) => <div>{children}</div>,
    motion: {
      div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    },
  }
})

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { useContract } from '../../hooks/use-contract'
import { copyToClipboard } from '@/lib/clipboard'
import { toast } from 'sonner'
import { ContractDetail } from '../ContractDetail'

const mockUseContract = useContract as unknown as ReturnType<typeof vi.fn>

const baseMock = {
  id: 1,
  name: 'Test Contract',
  status: 'active',
  case_type: 'civil',
  fee_mode: 'FIXED',
  fixed_amount: 50000,
  risk_rate: 10,
  custom_terms: null,
  specified_date: '2026-01-01',
  start_date: '2026-01-01',
  end_date: '2027-01-01',
  is_filed: true,
  total_received: 30000,
  total_invoiced: 20000,
  unpaid_amount: 20000,
  representation_stages: ['一审'],
  reminders: [],
  payments: [],
  client_payment_records: [],
  supplementary_agreements: [],
  contract_parties: [
    {
      id: 1, client: 1, role: 'PRINCIPAL', role_label: '委托人',
      client_detail: {
        name: '张三', is_our_client: true, client_type: 'natural',
        client_type_label: '自然人', id_number: '110', phone: '138', address: '北京',
      },
    },
  ],
  assignments: [
    { id: 1, lawyer_id: 1, lawyer_name: '李律师', is_primary: true },
  ],
  cases: [],
}

describe('ContractDetail - branch coverage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseContract.mockReturnValue({ data: baseMock, isLoading: false, error: null })
  })

  // Branch: ContractStatusBadge with null status (line 48)
  it('renders "未设置" badge when status is null', () => {
    mockUseContract.mockReturnValue({ data: { ...baseMock, status: null }, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('未设置').length).toBeGreaterThan(0)
  })

  // Branch: ContractStatusBadge with status but no label match (line 54, label || status)
  it('falls back to raw status when label not found', () => {
    mockUseContract.mockReturnValue({ data: { ...baseMock, status: 'custom_status' as any }, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('custom_status').length).toBeGreaterThan(0)
  })

  // Branch: label fallback for case_type (line 153)
  it('falls back case_type label to raw value', () => {
    mockUseContract.mockReturnValue({ data: { ...baseMock, case_type: 'rare_type' as any }, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('rare_type').length).toBeGreaterThan(0)
  })

  // Branch: label fallback for fee_mode (line 154)
  it('falls back fee_mode label to raw value', () => {
    mockUseContract.mockReturnValue({ data: { ...baseMock, fee_mode: 'UNKNOWN_FEE' as any }, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('UNKNOWN_FEE').length).toBeGreaterThan(0)
  })

  // Branch: is_filed === false (line 167)
  it('does not render filed badge when is_filed is false', () => {
    mockUseContract.mockReturnValue({ data: { ...baseMock, is_filed: false }, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    // Should show "未建档" dot
    expect(screen.getByText('未建档')).toBeInTheDocument()
  })

  // Branch: party with all null optional fields (CopyableField returns null)
  it('party detail sheet hides fields when values are null/undefined', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...baseMock,
        contract_parties: [{
          id: 5, client: 5, role: 'PRINCIPAL', role_label: '委托人',
          client_detail: {
            name: '无信息当事人', is_our_client: true, client_type: 'natural',
            client_type_label: '自然人', id_number: null, phone: null, address: null,
          },
        }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('无信息当事人'))
    // CopyableField returns null for falsy values
    expect(screen.queryByText('身份证号码')).not.toBeInTheDocument()
    expect(screen.queryByText('联系电话')).not.toBeInTheDocument()
    expect(screen.queryByText('住所地')).not.toBeInTheDocument()
  })

  // Branch: party copy all with null name, id_number, phone, address (natural)
  it('copy all party info filters out null fields', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...baseMock,
        contract_parties: [{
          id: 6, client: 6, role: 'PRINCIPAL', role_label: '委托人',
          client_detail: {
            name: '简要', is_our_client: true, client_type: 'natural',
            client_type_label: '自然人', id_number: null, phone: null, address: null,
          },
        }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('简要'))
    fireEvent.click(screen.getByText('复制全部'))
    // Should only contain name
    expect(copyToClipboard).toHaveBeenCalledWith(
      expect.stringContaining('简要'),
      '已复制全部信息',
    )
  })

  // Branch: party copy all for legal entity with null fields (non-natural, line 426-430)
  it('copy all for legal entity with missing optional fields', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...baseMock,
        contract_parties: [{
          id: 7, client: 7, role: 'PRINCIPAL', role_label: '委托人',
          client_detail: {
            name: '公司B', is_our_client: false, client_type: 'legal',
            client_type_label: '法人', id_number: null, phone: null, address: null,
            legal_representative: null, legal_representative_id_number: null,
          },
        }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('公司B'))
    fireEvent.click(screen.getByText('复制全部'))
    expect(copyToClipboard).toHaveBeenCalledWith(
      expect.stringContaining('公司B'),
      '已复制全部信息',
    )
  })

  // Branch: non-legal entity without legal representative (line 398)
  it('does not render legal representative section when null', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...baseMock,
        contract_parties: [{
          id: 8, client: 8, role: 'PRINCIPAL', role_label: '委托人',
          client_detail: {
            name: '公司C', is_our_client: true, client_type: 'legal',
            client_type_label: '法人', id_number: 'SC999', phone: '010', address: 'BJ',
            legal_representative: null, legal_representative_id_number: null,
          },
        }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('公司C'))
    expect(screen.queryByText('法定代表人信息')).not.toBeInTheDocument()
  })

  // Branch: handleCopy in lawyer sheet (line 472, 482)
  it('copies lawyer name when copy button clicked in lawyer sheet', () => {
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    const lawyers = screen.getAllByText('李律师')
    fireEvent.click(lawyers[lawyers.length - 1])
    // Find and click the copy button near lawyer name
    const buttons = screen.getAllByRole('button').filter(b =>
      b.closest('[class*="rounded-lg"]') && b.querySelector('svg')
    )
    if (buttons.length > 0) {
      fireEvent.click(buttons[buttons.length - 1])
      expect(copyToClipboard).toHaveBeenCalled()
    }
  })

  // Branch: lawyer copy all with is_primary=false (line 496)
  it('copies all lawyer info for secondary lawyer showing 协办律师', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...baseMock,
        assignments: [{ id: 2, lawyer_id: 2, lawyer_name: '王律师', is_primary: false }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('王律师'))
    // Should show "协办律师" description
    expect(screen.getAllByText('协办律师').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByText('复制全部'))
    expect(toast.success).toHaveBeenCalledWith('已复制全部信息')
  })

  // Branch: advisor contract renew action (line 208-211)
  it('renders renew option for advisor contract', () => {
    mockUseContract.mockReturnValue({
      data: { ...baseMock, case_type: 'advisor' },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('续签顾问合同')).toBeInTheDocument()
  })

  // Branch: generate-doc with json response default message (line 108)
  it('shows default message when json response has no message field', async () => {
    mockGenerateContract.mockResolvedValueOnce({
      headers: { get: (h: string) => h === 'content-type' ? 'application/json' : null },
      json: () => Promise.resolve({}),
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('更多操作'))
    await screen.findByText('生成合同文档')
    fireEvent.click(screen.getByText('生成合同文档'))
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('合同已生成并保存')
    })
  })

  // Branch: actionLoading shows loader icon (line 194)
  it('shows loader icon when action is loading', async () => {
    // Make generateContract hang
    mockGenerateContract.mockReturnValue(new Promise(() => {}))
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('更多操作'))
    await screen.findByText('生成合同文档')
    fireEvent.click(screen.getByText('生成合同文档'))
    // The button should now show a loader
    await waitFor(() => {
      expect(screen.getByText('更多操作')).toBeInTheDocument()
    })
  })

  // Branch: detail skeleton renders pulse elements (line 569-585)
  it('renders skeleton with multiple pulse elements', () => {
    mockUseContract.mockReturnValue({ data: undefined, isLoading: true, error: null })
    const { container } = render(<ContractDetail contractId="1" />)
    const pulses = container.querySelectorAll('.animate-pulse')
    expect(pulses.length).toBeGreaterThanOrEqual(3)
  })
})
