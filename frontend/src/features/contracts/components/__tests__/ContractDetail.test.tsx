vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

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
    deleteContract: { mutateAsync: vi.fn() },
    duplicateContract: { mutateAsync: vi.fn() },
    createCaseFromContract: { mutateAsync: vi.fn() },
  }),
}))

vi.mock('../../api', () => ({
  contractApi: { generateContract: vi.fn() },
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

import { render, screen, fireEvent } from '@testing-library/react'
import { useContract } from '../../hooks/use-contract'
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
})
