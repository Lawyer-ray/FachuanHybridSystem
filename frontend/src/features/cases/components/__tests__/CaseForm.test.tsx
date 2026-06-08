vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_CASES: '/admin/cases' },
  generatePath: { caseDetail: (id: string) => `/cases/${id}`, caseEdit: (id: string) => `/cases/${id}/edit` },
}))

vi.mock('../../hooks/use-case', () => ({ useCase: vi.fn() }))
vi.mock('../../hooks/use-case-mutations', () => ({
  useCaseMutations: () => ({
    createCaseFull: { mutate: vi.fn(), isPending: false },
    updateCase: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('../CauseSelector', () => ({
  CauseSelector: (props: any) => <div data-testid="cause-selector" />,
}))
vi.mock('../FeeCalculator', () => ({
  FeeCalculator: () => <div data-testid="fee-calculator" />,
}))
vi.mock('../CasePartySection', () => ({
  CasePartySection: () => <div data-testid="party-section" />,
}))
vi.mock('../CaseAssignmentSection', () => ({
  CaseAssignmentSection: () => <div data-testid="assignment-section" />,
}))
vi.mock('../CaseLogSection', () => ({
  CaseLogSection: () => <div data-testid="log-section" />,
}))
vi.mock('../CaseNumberSection', () => ({
  CaseNumberSection: () => <div data-testid="number-section" />,
}))
vi.mock('../AuthoritySection', () => ({
  AuthoritySection: () => <div data-testid="authority-section" />,
}))

vi.mock('../types', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../types')>()
  return {
    ...actual,
    caseFormSchema: { extend: () => ({}) },
  }
})

vi.mock('@hookform/resolvers/zod', () => ({
  zodResolver: () => () => ({}),
}))

import { render, screen } from '@testing-library/react'
import { useCase } from '../../hooks/use-case'
import { CaseForm } from '../CaseForm'

const mockUseCase = useCase as unknown as ReturnType<typeof vi.fn>

describe('CaseForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockUseCase.mockReturnValue({ data: null, isLoading: false, error: null })
  })

  it('renders create mode header', () => {
    render(<CaseForm mode="create" />)
    expect(screen.getByText('新建案件')).toBeInTheDocument()
  })

  it('renders save button in create mode', () => {
    render(<CaseForm mode="create" />)
    expect(screen.getByText('保存')).toBeInTheDocument()
  })

  it('renders cancel button', () => {
    render(<CaseForm mode="create" />)
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('renders form fields for case info', () => {
    render(<CaseForm mode="create" />)
    expect(screen.getByText('案件信息')).toBeInTheDocument()
  })

  it('shows loading state in edit mode', () => {
    mockUseCase.mockReturnValue({ data: null, isLoading: true, error: null })
    render(<CaseForm caseId="1" mode="edit" />)
    expect(document.querySelector('.animate-spin')).toBeInTheDocument()
  })

  it('shows error state in edit mode', () => {
    mockUseCase.mockReturnValue({ data: null, isLoading: false, error: new Error('not found') })
    render(<CaseForm caseId="1" mode="edit" />)
    expect(screen.getByText('加载案件数据失败')).toBeInTheDocument()
    expect(screen.getByText('返回')).toBeInTheDocument()
  })

  it('renders edit mode header', () => {
    mockUseCase.mockReturnValue({
      data: { id: 1, name: '编辑案件', status: 'active', case_type: 'litigation', parties: [], assignments: [], logs: [], case_numbers: [], supervising_authorities: [] },
      isLoading: false,
      error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    expect(screen.getByText('编辑案件')).toBeInTheDocument()
  })

  it('renders parties and assignments section in create mode', () => {
    render(<CaseForm mode="create" />)
    expect(screen.getByText('当事人')).toBeInTheDocument()
    expect(screen.getByText('指派律师')).toBeInTheDocument()
    expect(screen.getByText('主管机关')).toBeInTheDocument()
  })

  it('shows empty messages in create mode', () => {
    render(<CaseForm mode="create" />)
    expect(screen.getByText('暂无当事人')).toBeInTheDocument()
    expect(screen.getByText('暂未指派律师')).toBeInTheDocument()
    expect(screen.getByText('暂无主管机关')).toBeInTheDocument()
  })

  it('renders fee calculator', () => {
    render(<CaseForm mode="create" />)
    expect(screen.getByTestId('fee-calculator')).toBeInTheDocument()
  })

  it('renders additional sections in edit mode', () => {
    mockUseCase.mockReturnValue({
      data: { id: 1, name: '编辑案件', status: 'active', parties: [], assignments: [], logs: [], case_numbers: [], supervising_authorities: [] },
      isLoading: false,
      error: null,
    })
    render(<CaseForm caseId="1" mode="edit" />)
    expect(screen.getByText('案件当事人')).toBeInTheDocument()
    expect(screen.getByText('律师指派')).toBeInTheDocument()
    expect(screen.getByText('案件日志')).toBeInTheDocument()
    expect(screen.getByText('案号')).toBeInTheDocument()
    expect(screen.getByText('主管机关')).toBeInTheDocument()
  })
})
