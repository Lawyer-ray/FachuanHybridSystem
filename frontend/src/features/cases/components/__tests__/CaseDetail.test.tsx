vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_CASES: '/admin/cases' },
  generatePath: { caseEdit: (id: string) => `/cases/${id}/edit` },
}))

vi.mock('@/lib/date', () => ({ formatDateOnly: (v: string | null) => v ?? '-' }))
vi.mock('@/lib/format', () => ({ formatAmount: (v: number | null) => (v != null ? `¥${v}` : '-') }))

vi.mock('../../hooks/use-case', () => ({ useCase: vi.fn() }))
vi.mock('../../hooks/use-case-mutations', () => ({
  useCaseMutations: () => ({ deleteCase: { mutateAsync: vi.fn() } }),
}))
vi.mock('../../hooks/use-material-candidates', () => ({
  useMaterialCandidates: () => ({ data: [] }),
}))
vi.mock('../../hooks/use-template-bindings', () => ({
  useTemplateBindings: () => ({ data: { categories: [] } }),
}))
vi.mock('../../hooks/use-folder-binding', () => ({
  useFolderBinding: () => ({ data: null }),
}))

vi.mock('../CaseLogSection', () => ({
  CaseLogSection: () => <div data-testid="log-section" />,
}))
vi.mock('../CaseNumberSection', () => ({
  CaseNumberSection: () => <div data-testid="number-section" />,
}))
vi.mock('../CaseMaterialSection', () => ({
  CaseMaterialSection: () => <div data-testid="material-section" />,
}))
vi.mock('../CaseTemplateSection', () => ({
  CaseTemplateSection: () => <div data-testid="template-section" />,
}))
vi.mock('../CaseFolderSection', () => ({
  CaseFolderSection: () => <div data-testid="folder-section" />,
}))
vi.mock('../AuthoritySection', () => ({
  AuthoritySection: () => <div data-testid="authority-section" />,
}))
vi.mock('../CourtFilingSection', () => ({
  CourtFilingSection: () => <div data-testid="court-filing-section" />,
}))
vi.mock('../CourtGuaranteeSection', () => ({
  CourtGuaranteeSection: () => <div data-testid="court-guarantee-section" />,
}))
vi.mock('../AuthorizationMaterialsSection', () => ({
  AuthorizationMaterialsSection: () => <div data-testid="authorization-section" />,
}))
vi.mock('@/features/contacts', () => ({
  CaseContactSection: () => <div data-testid="contact-section" />,
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
import { useCase } from '../../hooks/use-case'
import { CaseDetail } from '../CaseDetail'

const mockUseCase = useCase as unknown as ReturnType<typeof vi.fn>

describe('CaseDetail', () => {
  const mockCase = {
    id: 1,
    name: '测试案件',
    status: 'active',
    case_type: 'civil',
    current_stage: 'first_trial',
    cause_of_action: '合同纠纷',
    target_amount: 100000,
    preservation_amount: null,
    start_date: '2026-01-01',
    effective_date: null,
    specified_date: null,
    contract_id: 5,
    is_filed: true,
    filing_number: '(2026)京0101民初123号',
    parties: [
      {
        id: 1,
        client_detail: { name: '张三', is_our_client: true, client_type: 'natural' },
        legal_status: 'plaintiff',
      },
    ],
    assignments: [
      { id: 1, lawyer_detail: { real_name: '李律师', username: 'li', phone: '00000000000' } },
    ],
    logs: [],
    chats: [],
    contacts: [],
    case_numbers: [],
    supervising_authorities: [],
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows loading skeleton initially', () => {
    mockUseCase.mockReturnValue({ data: undefined, isLoading: true, error: null })
    render(<CaseDetail caseId="1" />)
    expect(document.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('shows error state when case not found', () => {
    mockUseCase.mockReturnValue({ data: undefined, isLoading: false, error: new Error('not found') })
    render(<CaseDetail caseId="1" />)
    expect(screen.getByText('案件不存在')).toBeInTheDocument()
  })

  it('shows error state when data is null', () => {
    mockUseCase.mockReturnValue({ data: null, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    expect(screen.getByText('案件不存在')).toBeInTheDocument()
  })

  it('renders case name and status', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    expect(screen.getAllByText('测试案件').length).toBeGreaterThan(0)
    expect(screen.getAllByText('在办').length).toBeGreaterThan(0)
  })

  it('renders action buttons', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    expect(screen.getByText('返回列表')).toBeInTheDocument()
    expect(screen.getByText('删除')).toBeInTheDocument()
    expect(screen.getByText('编辑')).toBeInTheDocument()
  })

  it('renders tabs', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    expect(screen.getByText('基本信息')).toBeInTheDocument()
    expect(screen.getByText('案件人员')).toBeInTheDocument()
    expect(screen.getByText('案件进展')).toBeInTheDocument()
    expect(screen.getByText('文档生成')).toBeInTheDocument()
    expect(screen.getByText('一张网立案')).toBeInTheDocument()
  })

  it('shows filed status', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    expect(screen.getByText(/已建档/)).toBeInTheDocument()
  })

  it('shows unfired status', () => {
    mockUseCase.mockReturnValue({
      data: { ...mockCase, is_filed: false, filing_number: null },
      isLoading: false,
      error: null,
    })
    render(<CaseDetail caseId="1" />)
    expect(screen.getByText('未建档')).toBeInTheDocument()
  })

  it('shows primary lawyer name', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    expect(screen.getByText('李律师')).toBeInTheDocument()
  })

  it('shows unassigned when no lawyer', () => {
    mockUseCase.mockReturnValue({
      data: { ...mockCase, assignments: [] },
      isLoading: false,
      error: null,
    })
    render(<CaseDetail caseId="1" />)
    expect(screen.getByText('未指派')).toBeInTheDocument()
  })

  it('switches tabs on click', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    fireEvent.click(screen.getByText('案件人员'))
    expect(screen.getByText('案件当事人')).toBeInTheDocument()
    expect(screen.getByText('律师指派')).toBeInTheDocument()
  })

  it('shows parties in parties tab', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    fireEvent.click(screen.getByText('案件人员'))
    expect(screen.getByText('张三')).toBeInTheDocument()
  })

  it('shows empty party message', () => {
    mockUseCase.mockReturnValue({
      data: { ...mockCase, parties: [], assignments: [] },
      isLoading: false,
      error: null,
    })
    render(<CaseDetail caseId="1" />)
    fireEvent.click(screen.getByText('案件人员'))
    expect(screen.getByText('暂无当事人')).toBeInTheDocument()
    expect(screen.getByText('暂无指派律师')).toBeInTheDocument()
  })

  it('shows case type badge', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    expect(screen.getAllByText('民事').length).toBeGreaterThan(0)
  })

  it('shows stage label', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    expect(screen.getAllByText('一审').length).toBeGreaterThan(0)
  })

  it('shows contract link when contract_id exists', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    expect(screen.getByText('合同 #5')).toBeInTheDocument()
  })

  it('renders basic info tab by default', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    expect(screen.getByText('案件信息')).toBeInTheDocument()
    expect(screen.getByText('日期信息')).toBeInTheDocument()
  })

  it('switches to progress tab and shows logs section', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    fireEvent.click(screen.getByText('案件进展'))
    expect(screen.getByText('案件日志')).toBeInTheDocument()
    expect(screen.getByText('案件群聊')).toBeInTheDocument()
  })

  it('switches to documents tab', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    fireEvent.click(screen.getByText('文档生成'))
    expect(screen.getByTestId('authorization-section')).toBeInTheDocument()
    expect(screen.getByTestId('template-section')).toBeInTheDocument()
    expect(screen.getByTestId('folder-section')).toBeInTheDocument()
  })

  it('shows empty chats message', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    fireEvent.click(screen.getByText('案件进展'))
    expect(screen.getByText('暂无关联群聊')).toBeInTheDocument()
  })

  it('shows chats when available', () => {
    mockUseCase.mockReturnValue({
      data: {
        ...mockCase,
        chats: [{ id: 1, name: '案件群', platform: 'wechat', is_active: true }],
      },
      isLoading: false,
      error: null,
    })
    render(<CaseDetail caseId="1" />)
    fireEvent.click(screen.getByText('案件进展'))
    expect(screen.getByText('案件群')).toBeInTheDocument()
    expect(screen.getByText('有效')).toBeInTheDocument()
  })

  it('opens delete dialog on delete click', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    fireEvent.click(screen.getByText('删除'))
    expect(screen.getByText('确认删除案件')).toBeInTheDocument()
    expect(screen.getByText('确认删除')).toBeInTheDocument()
  })

  it('renders court filing tab', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    fireEvent.click(screen.getByText('一张网立案'))
    expect(screen.getByTestId('court-filing-section')).toBeInTheDocument()
    expect(screen.getByTestId('court-guarantee-section')).toBeInTheDocument()
  })

  it('renders party and non-party materials tabs', () => {
    mockUseCase.mockReturnValue({ data: mockCase, isLoading: false, error: null })
    render(<CaseDetail caseId="1" />)
    fireEvent.click(screen.getByText('当事人材料'))
    expect(screen.getByTestId('material-section')).toBeInTheDocument()
    fireEvent.click(screen.getByText('非当事人材料'))
    expect(screen.getByTestId('material-section')).toBeInTheDocument()
  })
})
