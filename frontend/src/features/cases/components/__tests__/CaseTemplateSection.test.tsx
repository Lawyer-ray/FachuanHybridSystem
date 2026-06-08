import { render, screen, cleanup } from '@testing-library/react'
import { CaseTemplateSection } from '../CaseTemplateSection'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})
vi.mock('../../hooks/use-template-mutations', () => ({
  useTemplateMutations: () => ({
    generateTemplate: { mutate: vi.fn(), isPending: false },
    unbindTemplate: { mutate: vi.fn() },
    bindTemplate: { mutate: vi.fn(), isPending: false },
  }),
}))
vi.mock('../../hooks/use-template-bindings', () => ({
  useAvailableTemplates: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}))

const mockCategories = [
  {
    category: 'case_pleading',
    category_display: '起诉状类',
    templates: [
      {
        template_id: 1,
        name: '民事起诉状（通用）',
        binding_id: 10,
        binding_source: 'manual_bound',
        binding_source_display: '手动绑定',
      },
      {
        template_id: 2,
        name: '行政起诉状',
        binding_id: null,
        binding_source: 'auto_matched',
        binding_source_display: '自动匹配',
      },
    ],
  },
  {
    category: 'case_evidence',
    category_display: '证据类',
    templates: [
      {
        template_id: 3,
        name: '证据目录',
        binding_id: 20,
        binding_source: 'manual_bound',
        binding_source_display: '手动绑定',
      },
    ],
  },
]

const mockParties = [
  { client: 1, client_detail: { name: '张三' }, legal_status: 'plaintiff' },
  { client: 2, client_detail: { name: '李四' }, legal_status: 'defendant' },
]

describe('CaseTemplateSection', () => {
  beforeEach(() => cleanup())

  it('shows empty state when no categories', () => {
    render(<CaseTemplateSection categories={[]} parties={[]} caseId={1} />)
    expect(screen.getByText('暂无绑定模板')).toBeInTheDocument()
  })

  it('shows bind button when empty', () => {
    render(<CaseTemplateSection categories={[]} parties={[]} caseId={1} />)
    expect(screen.getByText('绑定模板')).toBeInTheDocument()
  })

  it('renders template count', () => {
    render(<CaseTemplateSection categories={mockCategories} parties={mockParties} caseId={1} />)
    expect(screen.getByText(/3 个模板/)).toBeInTheDocument()
  })

  it('renders category groups', () => {
    render(<CaseTemplateSection categories={mockCategories} parties={mockParties} caseId={1} />)
    expect(screen.getByText('起诉状类')).toBeInTheDocument()
    expect(screen.getByText('证据类')).toBeInTheDocument()
  })

  it('renders template names', () => {
    render(<CaseTemplateSection categories={mockCategories} parties={mockParties} caseId={1} />)
    expect(screen.getByText('民事起诉状（通用）')).toBeInTheDocument()
    expect(screen.getByText('行政起诉状')).toBeInTheDocument()
    expect(screen.getByText('证据目录')).toBeInTheDocument()
  })

  it('shows binding source for non-manual bindings', () => {
    render(<CaseTemplateSection categories={mockCategories} parties={mockParties} caseId={1} />)
    expect(screen.getByText('自动匹配')).toBeInTheDocument()
  })

  it('renders bind button when has categories', () => {
    render(<CaseTemplateSection categories={mockCategories} parties={mockParties} caseId={1} />)
    expect(screen.getByText('绑定')).toBeInTheDocument()
  })

  it('shows category count in header', () => {
    render(<CaseTemplateSection categories={mockCategories} parties={mockParties} caseId={1} />)
    // "(2)" for first category, "(1)" for second
    expect(screen.getByText('(2)')).toBeInTheDocument()
    expect(screen.getByText('(1)')).toBeInTheDocument()
  })

  it('renders category group headers', () => {
    render(<CaseTemplateSection categories={mockCategories} parties={mockParties} caseId={1} />)
    // The category_display is rendered
    expect(screen.getByText('起诉状类')).toBeInTheDocument()
  })

  it('renders with single category', () => {
    const singleCat = [mockCategories[0]]
    render(<CaseTemplateSection categories={singleCat} parties={[]} caseId={1} />)
    expect(screen.getByText('起诉状类')).toBeInTheDocument()
    expect(screen.getByText(/2 个模板/)).toBeInTheDocument()
  })
})
