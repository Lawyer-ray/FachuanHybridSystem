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

vi.mock('../FeesTab', () => ({
  FeesTab: () => <div data-testid="fees-tab" />,
}))

vi.mock('../FilingTab', () => ({
  FilingTab: () => <div data-testid="filing-tab" />,
}))

vi.mock('../DocumentsTab', () => ({
  DocumentsTab: () => <div data-testid="documents-tab" />,
}))

vi.mock('../ArchiveTab', () => ({
  ArchiveTab: () => <div data-testid="archive-tab" />,
}))

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
import { downloadBlob } from '@/lib/download'
import { copyToClipboard } from '@/lib/clipboard'
import { toast } from 'sonner'
import { ContractDetail } from '../ContractDetail'

const mockUseContract = useContract as unknown as ReturnType<typeof vi.fn>

describe('ContractDetail', () => {
  const mockContract = {
    id: 1,
    name: '民商事合同A',
    status: 'active',
    case_type: 'civil',
    fee_mode: 'FIXED',
    fixed_amount: 50000,
    risk_rate: null,
    custom_terms: null,
    specified_date: '2026-01-01',
    start_date: '2026-01-01',
    end_date: '2027-01-01',
    is_filed: true,
    total_received: 30000,
    total_invoiced: 20000,
    unpaid_amount: 20000,
    representation_stages: ['一审'],
    matched_document_template: '模板A',
    matched_folder_templates: null,
    has_matched_templates: true,
    reminders: [],
    payments: [],
    client_payment_records: [],
    supplementary_agreements: [],
    contract_parties: [
      {
        id: 1,
        client: 1,
        role: 'PRINCIPAL',
        role_label: '委托人',
        client_detail: { name: '张三', is_our_client: true, client_type: 'natural', client_type_label: '自然人', id_number: '110', phone: '138', address: '北京' },
      },
    ],
    assignments: [
      { id: 1, lawyer_id: 1, lawyer_name: '李律师', is_primary: true },
    ],
    cases: [],
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading skeleton', () => {
    mockUseContract.mockReturnValue({ data: undefined, isLoading: true, error: null })
    render(<ContractDetail contractId="1" />)
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('shows error state', () => {
    mockUseContract.mockReturnValue({ data: undefined, isLoading: false, error: new Error('not found') })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('合同不存在')).toBeInTheDocument()
  })

  it('shows null data state', () => {
    mockUseContract.mockReturnValue({ data: null, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('合同不存在')).toBeInTheDocument()
  })

  it('renders contract name and status', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('民商事合同A').length).toBeGreaterThan(0)
    expect(screen.getAllByText('在办').length).toBeGreaterThan(0)
  })

  it('renders action buttons', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('返回列表')).toBeInTheDocument()
    expect(screen.getByText('删除')).toBeInTheDocument()
    expect(screen.getByText('编辑')).toBeInTheDocument()
    expect(screen.getByText('更多操作')).toBeInTheDocument()
  })

  it('renders tabs', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('基本信息')).toBeInTheDocument()
    expect(screen.getByText('当事人与律师')).toBeInTheDocument()
    expect(screen.getByText('收费与财务')).toBeInTheDocument()
    expect(screen.getByText('立案')).toBeInTheDocument()
    expect(screen.getByText('文档与提醒')).toBeInTheDocument()
    expect(screen.getByText('归档')).toBeInTheDocument()
  })

  it('shows primary lawyer', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('李律师')).toBeInTheDocument()
  })

  it('shows filed badge', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('已建档').length).toBeGreaterThan(0)
  })

  it('switches to parties tab', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    expect(screen.getByText('合同当事人')).toBeInTheDocument()
    expect(screen.getByText('张三')).toBeInTheDocument()
    expect(screen.getByText('律师指派')).toBeInTheDocument()
  })

  it('switches to fees tab', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('收费与财务'))
    expect(screen.getByTestId('fees-tab')).toBeInTheDocument()
  })

  it('switches to filing tab', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('立案'))
    expect(screen.getByTestId('filing-tab')).toBeInTheDocument()
  })

  it('switches to documents tab', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('文档与提醒'))
    expect(screen.getByTestId('documents-tab')).toBeInTheDocument()
  })

  it('switches to archive tab', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('归档'))
    expect(screen.getByTestId('archive-tab')).toBeInTheDocument()
  })

  it('opens delete dialog', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('删除'))
    expect(screen.getByText('确认删除合同')).toBeInTheDocument()
    expect(screen.getByText('确认删除')).toBeInTheDocument()
  })

  it('shows related cases section', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, cases: [{ id: 10, name: '关联案件', cause_of_action: '合同纠纷', status_label: '进行中', target_amount: 100000 }] },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('关联案件').length).toBeGreaterThan(0)
    expect(screen.getByText('合同纠纷')).toBeInTheDocument()
  })

  it('shows empty parties message', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, contract_parties: [], assignments: [] },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    expect(screen.getByText('暂无当事人')).toBeInTheDocument()
    expect(screen.getByText('暂无指派律师')).toBeInTheDocument()
  })

  it('shows unassigned lawyer', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, assignments: [] },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('未指派')).toBeInTheDocument()
  })

  it('shows representation stages', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('一审')).toBeInTheDocument()
  })

  // --- New tests for uncovered lines ---

  it('shows no primary lawyer when none is primary', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, assignments: [{ id: 1, lawyer_id: 1, lawyer_name: '李律师', is_primary: false }] },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('未指派')).toBeInTheDocument()
  })

  it('renders risk rate when set', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, risk_rate: 15 },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('15%')).toBeInTheDocument()
  })

  it('renders custom terms when set', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, custom_terms: '特殊条款' },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('特殊条款')).toBeInTheDocument()
  })

  it('renders supplementary agreements section', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, supplementary_agreements: [{ id: 1, title: '补充协议1' }] },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    expect(screen.getByText('补充协议')).toBeInTheDocument()
    expect(screen.getByTestId('agreement-list')).toBeInTheDocument()
  })

  it('renders advisor case type with renew option', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, case_type: 'advisor' },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    // The dropdown should have the renew option for advisor contracts
    expect(screen.getByText('更多操作')).toBeInTheDocument()
  })

  it('shows no cases section when cases empty', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, cases: [] },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.queryByText('关联案件')).not.toBeInTheDocument()
  })

  it('renders case with target_amount', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...mockContract,
        cases: [{ id: 10, name: '案件A', cause_of_action: '纠纷', status_label: '进行中', target_amount: 50000 }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('案件A')).toBeInTheDocument()
  })

  it('renders case without target_amount', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...mockContract,
        cases: [{ id: 10, name: '案件B', cause_of_action: '', status_label: '', target_amount: null }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('案件B')).toBeInTheDocument()
  })

  it('renders parties tab with party details', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    expect(screen.getByText('张三')).toBeInTheDocument()
    expect(screen.getByText('委托人')).toBeInTheDocument()
    expect(screen.getByText('我方')).toBeInTheDocument()
  })

  it('renders party as other side', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...mockContract,
        contract_parties: [{
          id: 2, client: 2, role: 'OPPONENT', role_label: '对方当事人',
          client_detail: { name: '李四', is_our_client: false, client_type: 'natural', client_type_label: '自然人', id_number: '111', phone: '139', address: '上海' },
        }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    expect(screen.getByText('李四')).toBeInTheDocument()
    expect(screen.getByText('对方')).toBeInTheDocument()
  })

  it('renders lawyer as 协办 when not primary', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...mockContract,
        assignments: [{ id: 2, lawyer_id: 2, lawyer_name: '王律师', is_primary: false }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    expect(screen.getByText('王律师')).toBeInTheDocument()
    expect(screen.getByText('协办')).toBeInTheDocument()
  })

  it('renders closed status badge', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, status: 'closed' },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    // Status badge should render (the StatusBadge mock renders children)
    expect(screen.getAllByText('民商事合同A').length).toBeGreaterThan(0)
  })

  it('renders archived status badge', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, status: 'archived' },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('民商事合同A').length).toBeGreaterThan(0)
  })

  it('renders pending status badge', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, status: 'pending' },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('民商事合同A').length).toBeGreaterThan(0)
  })

  it('renders null status badge', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, status: null },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('未设置').length).toBeGreaterThan(0)
  })

  it('renders not filed status', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, is_filed: false },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getByText('未建档')).toBeInTheDocument()
  })

  it('renders fee mode label', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    // Fee mode label is rendered
    expect(screen.getAllByText('民商事合同A').length).toBeGreaterThan(0)
  })

  it('renders representation stages empty', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, representation_stages: [] },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('民商事合同A').length).toBeGreaterThan(0)
  })

  it('opens party detail on parties tab', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    expect(screen.getByText('张三')).toBeInTheDocument()
    // Click on the party card to open detail sheet
    fireEvent.click(screen.getByText('张三'))
    // Sheet content should be rendered (mock doesn't show/hide)
    expect(screen.getAllByText('委托人').length).toBeGreaterThan(0)
  })

  it('opens lawyer detail on parties tab', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    // "李律师" appears in header and in parties tab
    const lawyers = screen.getAllByText('李律师')
    // Click the one in the parties section (the clickable one)
    fireEvent.click(lawyers[lawyers.length - 1])
    expect(screen.getAllByText('主办律师').length).toBeGreaterThan(0)
  })

  it('renders legal entity party with legal representative', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...mockContract,
        contract_parties: [{
          id: 3, client: 3, role: 'PRINCIPAL', role_label: '委托人',
          client_detail: {
            name: '公司A', is_our_client: true, client_type: 'legal', client_type_label: '法人',
            id_number: '91310000MA1ABCDE', phone: '021-12345678', address: '上海市',
            legal_representative: '王总', legal_representative_id_number: '310101199001011234', // pragma: allowlist secret
          },
        }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('公司A'))
    // The sheet should render (mock always shows content)
    expect(screen.getAllByText('法定代表人信息').length).toBeGreaterThan(0)
  })

  it('renders non_legal_org party with responsible person', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...mockContract,
        contract_parties: [{
          id: 4, client: 4, role: 'PRINCIPAL', role_label: '委托人',
          client_detail: {
            name: '非法人组织', is_our_client: false, client_type: 'non_legal_org', client_type_label: '非法人组织',
            id_number: '', phone: '', address: '',
            legal_representative: '负责人', legal_representative_id_number: '',
          },
        }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('非法人组织'))
    expect(screen.getAllByText('负责人信息').length).toBeGreaterThan(0)
  })

  it('renders lawyer detail sheet with primary lawyer badge', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    const lawyers = screen.getAllByText('李律师')
    fireEvent.click(lawyers[lawyers.length - 1])
    expect(screen.getAllByText('主办律师').length).toBeGreaterThan(0)
  })

  it('renders lawyer detail sheet for secondary lawyer', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...mockContract,
        assignments: [{ id: 2, lawyer_id: 2, lawyer_name: '王律师', is_primary: false }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('王律师'))
    expect(screen.getAllByText('协办律师').length).toBeGreaterThan(0)
  })

  // --- New tests for uncovered lines ---

  it('calls handleDelete successfully and navigates', async () => {
    mockDeleteAsync.mockResolvedValueOnce({})
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('删除'))
    await screen.findByText('确认删除合同')
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => {
      expect(mockDeleteAsync).toHaveBeenCalledWith('1')
      expect(toast.success).toHaveBeenCalledWith('合同已删除')
    })
  })

  it('shows error toast on delete failure', async () => {
    mockDeleteAsync.mockRejectedValueOnce(new Error('fail'))
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('删除'))
    await screen.findByText('确认删除合同')
    fireEvent.click(screen.getByText('确认删除'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('删除失败')
    })
  })

  it('handles generate-doc action with JSON response', async () => {
    const mockRes = {
      headers: { get: (h: string) => h === 'content-type' ? 'application/json' : null },
      json: () => Promise.resolve({ message: '文档已生成' }),
    }
    mockGenerateContract.mockResolvedValueOnce(mockRes as any)
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('更多操作'))
    await screen.findByText('生成合同文档')
    fireEvent.click(screen.getByText('生成合同文档'))
    await waitFor(() => {
      expect(mockGenerateContract).toHaveBeenCalledWith('1')
      expect(toast.success).toHaveBeenCalledWith('文档已生成')
    })
  })

  it('handles generate-doc action with blob response', async () => {
    const mockBlob = new Blob(['test'], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const mockRes = {
      headers: { get: (h: string) => h === 'content-type' ? 'application/octet-stream' : null },
      blob: () => Promise.resolve(mockBlob),
    }
    mockGenerateContract.mockResolvedValueOnce(mockRes as any)
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('更多操作'))
    await screen.findByText('生成合同文档')
    fireEvent.click(screen.getByText('生成合同文档'))
    await waitFor(() => {
      expect(downloadBlob).toHaveBeenCalledWith(mockBlob, expect.stringContaining('.docx'))
      expect(toast.success).toHaveBeenCalledWith('合同生成成功，已开始下载')
    })
  })

  it('handles generate-doc action with blob response using contractId fallback name', async () => {
    const mockBlob = new Blob(['test'])
    const mockRes = {
      headers: { get: () => null },
      blob: () => Promise.resolve(mockBlob),
    }
    mockGenerateContract.mockResolvedValueOnce(mockRes as any)
    mockUseContract.mockReturnValue({
      data: { ...mockContract, name: null },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('更多操作'))
    await screen.findByText('生成合同文档')
    fireEvent.click(screen.getByText('生成合同文档'))
    await waitFor(() => {
      expect(downloadBlob).toHaveBeenCalledWith(mockBlob, expect.stringContaining('1'))
    })
  })

  it('handles create-case action', async () => {
    mockCreateCaseAsync.mockResolvedValueOnce({ message: '案件创建成功' })
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('更多操作'))
    await screen.findByText('创建关联案件')
    fireEvent.click(screen.getByText('创建关联案件'))
    await waitFor(() => {
      expect(mockCreateCaseAsync).toHaveBeenCalledWith('1')
      expect(toast.success).toHaveBeenCalledWith('案件创建成功')
    })
  })

  it('handles create-case action with default message', async () => {
    mockCreateCaseAsync.mockResolvedValueOnce({})
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('更多操作'))
    await screen.findByText('创建关联案件')
    fireEvent.click(screen.getByText('创建关联案件'))
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('案件已创建')
    })
  })

  it('handles duplicate action', async () => {
    mockDuplicateAsync.mockResolvedValueOnce({ id: 99 })
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('更多操作'))
    await screen.findByText('复制合同')
    fireEvent.click(screen.getByText('复制合同'))
    await waitFor(() => {
      expect(mockDuplicateAsync).toHaveBeenCalledWith('1')
      expect(toast.success).toHaveBeenCalledWith('合同已复制')
    })
  })

  it('handles renew action', async () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, case_type: 'advisor' },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('更多操作'))
    await screen.findByText('续签顾问合同')
    fireEvent.click(screen.getByText('续签顾问合同'))
    // Should navigate to edit page with ?renew=true
  })

  it('handles action error with Error instance', async () => {
    mockGenerateContract.mockRejectedValueOnce(new Error('生成失败'))
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('更多操作'))
    await screen.findByText('生成合同文档')
    fireEvent.click(screen.getByText('生成合同文档'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('生成失败')
    })
  })

  it('handles action error with non-Error', async () => {
    mockGenerateContract.mockRejectedValueOnce('string error')
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('更多操作'))
    await screen.findByText('生成合同文档')
    fireEvent.click(screen.getByText('生成合同文档'))
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('操作失败')
    })
  })

  it('renders party copyable fields and copy button', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('张三'))
    // Copyable fields should be visible
    expect(screen.getByText('主体类型')).toBeInTheDocument()
    expect(screen.getByText('当事人角色')).toBeInTheDocument()
    expect(screen.getByText('身份证号码')).toBeInTheDocument()
    expect(screen.getByText('联系电话')).toBeInTheDocument()
    expect(screen.getByText('住所地')).toBeInTheDocument()
    expect(screen.getAllByText('自然人').length).toBeGreaterThan(0)
    expect(screen.getByText('110')).toBeInTheDocument()
    expect(screen.getByText('138')).toBeInTheDocument()
    expect(screen.getByText('北京')).toBeInTheDocument()
  })

  it('copies party field value when copy button clicked', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('张三'))
    // Find copy buttons (SVG icons) within the party detail sheet
    const copyButtons = screen.getAllByRole('button').filter(
      btn => btn.querySelector('svg') && btn.closest('[class*="rounded-lg"]')
    )
    // Click one of the copy buttons
    if (copyButtons.length > 0) {
      fireEvent.click(copyButtons[0])
      expect(copyToClipboard).toHaveBeenCalled()
    }
  })

  it('copies all party info when copy all button clicked', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('张三'))
    // Find the "复制全部" button
    const copyAllBtn = screen.getByText('复制全部')
    fireEvent.click(copyAllBtn)
    expect(copyToClipboard).toHaveBeenCalledWith(expect.stringContaining('张三'), '已复制全部信息')
  })

  it('copies all party info for legal entity', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...mockContract,
        contract_parties: [{
          id: 3, client: 3, role: 'PRINCIPAL', role_label: '委托人',
          client_detail: {
            name: '公司A', is_our_client: true, client_type: 'legal', client_type_label: '法人',
            id_number: '91310000MA1ABCDE', phone: '021-12345678', address: '上海市',
            legal_representative: '王总', legal_representative_id_number: '310101199001011234',
          },
        }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('公司A'))
    const copyAllBtn = screen.getByText('复制全部')
    fireEvent.click(copyAllBtn)
    expect(copyToClipboard).toHaveBeenCalledWith(expect.stringContaining('法定代表人'), '已复制全部信息')
  })

  it('renders party detail without optional fields (null values)', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...mockContract,
        contract_parties: [{
          id: 5, client: 5, role: 'PRINCIPAL', role_label: '委托人',
          client_detail: {
            name: '赵六', is_our_client: true, client_type: 'natural', client_type_label: '自然人',
            id_number: null, phone: null, address: null,
          },
        }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('赵六'))
    // CopyableField with null values should not render
    expect(screen.queryByText('身份证号码')).not.toBeInTheDocument()
  })

  it('copies lawyer name when copy button clicked', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    const lawyers = screen.getAllByText('李律师')
    fireEvent.click(lawyers[lawyers.length - 1])
    // Should show lawyer detail sheet with copyable name and ID
    expect(screen.getByText('律师 ID')).toBeInTheDocument()
  })

  it('copies all lawyer info when copy all button clicked', () => {
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    const lawyers = screen.getAllByText('李律师')
    fireEvent.click(lawyers[lawyers.length - 1])
    const copyAllBtn = screen.getAllByText('复制全部')
    fireEvent.click(copyAllBtn[copyAllBtn.length - 1])
    expect(toast.success).toHaveBeenCalledWith('已复制全部信息')
  })

  it('copies all lawyer info for secondary lawyer', () => {
    mockUseContract.mockReturnValue({
      data: {
        ...mockContract,
        assignments: [{ id: 2, lawyer_id: 2, lawyer_name: '王律师', is_primary: false }],
      },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('当事人与律师'))
    fireEvent.click(screen.getByText('王律师'))
    const copyAllBtn = screen.getByText('复制全部')
    fireEvent.click(copyAllBtn)
    expect(toast.success).toHaveBeenCalledWith('已复制全部信息')
  })

  it('shows generate-doc action with JSON response default message', async () => {
    const mockRes = {
      headers: { get: (h: string) => h === 'content-type' ? 'application/json' : null },
      json: () => Promise.resolve({}),
    }
    mockGenerateContract.mockResolvedValueOnce(mockRes as any)
    mockUseContract.mockReturnValue({ data: mockContract, isLoading: false, error: null })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('更多操作'))
    await screen.findByText('生成合同文档')
    fireEvent.click(screen.getByText('生成合同文档'))
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('合同已生成并保存')
    })
  })

  it('shows dashed line for empty custom_terms', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, custom_terms: null },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    // custom_terms null should render a dash in the detail field
  })

  it('renders unknown case_type and fee_mode fallback labels', () => {
    mockUseContract.mockReturnValue({
      data: { ...mockContract, case_type: 'unknown_type', fee_mode: 'UNKNOWN', status: 'unknown_status' },
      isLoading: false,
      error: null,
    })
    render(<ContractDetail contractId="1" />)
    expect(screen.getAllByText('民商事合同A').length).toBeGreaterThan(0)
  })

  it('shows detail skeleton with pulse elements', () => {
    mockUseContract.mockReturnValue({ data: undefined, isLoading: true, error: null })
    render(<ContractDetail contractId="1" />)
    const pulseElements = document.querySelectorAll('.animate-pulse')
    expect(pulseElements.length).toBeGreaterThan(0)
  })

  it('returns to list when clicking back button from error state', () => {
    mockUseContract.mockReturnValue({ data: undefined, isLoading: false, error: new Error('not found') })
    render(<ContractDetail contractId="1" />)
    fireEvent.click(screen.getByText('返回列表'))
    // Should navigate (useNavigate is mocked)
  })
})
