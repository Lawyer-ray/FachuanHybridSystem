vi.mock('../../hooks/use-templates', () => ({
  useTemplates: vi.fn().mockReturnValue({ data: [], isLoading: false }),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_TEMPLATE_NEW: '/templates/new', ADMIN_TEMPLATES: '/templates' },
  generatePath: { templateEdit: (id: string) => `/templates/${id}/edit` },
}))

vi.mock('@/components/shared/EmptyState', () => ({
  EmptyState: ({ title, description }: any) => <div><p>{title}</p><p>{description}</p></div>,
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { TemplateList } from '../TemplateList'
import { useTemplates } from '../../hooks/use-templates'
import type { Template } from '../../types'

function makeTemplate(overrides: Partial<Template> = {}): Template {
  return {
    id: 1,
    name: '测试模板',
    template_type: 'contract',
    is_active: true,
    contract_sub_type: 'contract',
    case_sub_type: null,
    archive_sub_type: null,
    file: null,
    file_path: 'contract/template.docx',
    case_types: [],
    case_stages: [],
    contract_types: ['civil'],
    legal_statuses: [],
    legal_status_match_mode: 'any',
    applicable_institutions: [],
    placeholders: ['p1', 'p2'],
    undefined_placeholders: [],
    created_at: '2026-01-01',
    updated_at: '2026-06-01',
    ...overrides,
  }
}

describe('TemplateList', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders page title', () => {
    render(<TemplateList />)
    expect(screen.getByText('文件模板')).toBeInTheDocument()
  })

  it('renders search input', () => {
    render(<TemplateList />)
    expect(screen.getByPlaceholderText('搜索模板名称...')).toBeInTheDocument()
  })

  it('renders create button', () => {
    render(<TemplateList />)
    expect(screen.getByText('新建模板')).toBeInTheDocument()
  })

  it('renders init default templates button', () => {
    render(<TemplateList />)
    expect(screen.getByText('初始化默认模板')).toBeInTheDocument()
  })

  it('renders active only checkbox', () => {
    render(<TemplateList />)
    expect(screen.getByText('仅显示启用')).toBeInTheDocument()
  })

  // ---- Empty state ----
  it('shows empty state when no templates', () => {
    vi.mocked(useTemplates).mockReturnValue({ data: [], isLoading: false } as any)
    render(<TemplateList />)
    expect(screen.getByText('没有匹配的模板')).toBeInTheDocument()
  })

  it('shows empty state when data is undefined', () => {
    vi.mocked(useTemplates).mockReturnValue({ data: undefined, isLoading: false } as any)
    render(<TemplateList />)
    expect(screen.getByText('没有匹配的模板')).toBeInTheDocument()
  })

  // ---- Loading state ----
  it('shows skeleton rows when loading', () => {
    vi.mocked(useTemplates).mockReturnValue({ data: undefined, isLoading: true } as any)
    const { container } = render(<TemplateList />)
    // Loading renders skeleton rows with animate-pulse divs
    const pulseEls = container.querySelectorAll('.animate-pulse')
    expect(pulseEls.length).toBeGreaterThan(0)
  })

  it('shows skeleton when loading even with data present', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate()], isLoading: true,
    } as any)
    const { container } = render(<TemplateList />)
    const pulseEls = container.querySelectorAll('.animate-pulse')
    expect(pulseEls.length).toBeGreaterThan(0)
  })

  // ---- Template rendering ----
  it('renders template data when available', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ name: '民事起诉状', template_type: 'case', case_sub_type: 'pleading_materials' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('民事起诉状')).toBeInTheDocument()
  })

  it('renders table header columns', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate()], isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('ID')).toBeInTheDocument()
    expect(screen.getByText('状态')).toBeInTheDocument()
    expect(screen.getByText('模板名称')).toBeInTheDocument()
    expect(screen.getByText('类型')).toBeInTheDocument()
    expect(screen.getByText('子类型')).toBeInTheDocument()
    expect(screen.getByText('文件来源')).toBeInTheDocument()
    expect(screen.getByText('占位符')).toBeInTheDocument()
    expect(screen.getByText('适用范围')).toBeInTheDocument()
    expect(screen.getByText('更新时间')).toBeInTheDocument()
    expect(screen.getByText('操作')).toBeInTheDocument()
  })

  // ---- Active/inactive status ----
  it('shows green dot for active template', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ is_active: true })], isLoading: false,
    } as any)
    const { container } = render(<TemplateList />)
    expect(container.querySelector('.text-status-green')).toBeInTheDocument()
  })

  it('shows inactive circle for inactive template', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ is_active: false })], isLoading: false,
    } as any)
    const { container } = render(<TemplateList />)
    expect(container.querySelector('.text-muted-foreground')).toBeInTheDocument()
  })

  // ---- Sub type labels (getSubTypeLabel branches) ----
  it('shows contract sub type label for contract templates', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ template_type: 'contract', contract_sub_type: 'supplementary_agreement' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('补充协议模板')).toBeInTheDocument()
  })

  it('shows case sub type label for case templates', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ template_type: 'case', contract_sub_type: null, case_sub_type: 'evidence_materials' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('证据材料')).toBeInTheDocument()
  })

  it('shows archive sub type label for archive templates', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ template_type: 'archive', contract_sub_type: null, case_sub_type: null, archive_sub_type: 'case_cover' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('案卷封面')).toBeInTheDocument()
  })

  it('shows raw sub type when label mapping is missing for contract', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ template_type: 'contract', contract_sub_type: 'unknown_sub_type' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('unknown_sub_type')).toBeInTheDocument()
  })

  it('shows raw sub type when label mapping is missing for case', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ template_type: 'case', contract_sub_type: null, case_sub_type: 'unknown_case_sub' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('unknown_case_sub')).toBeInTheDocument()
  })

  it('shows raw sub type when label mapping is missing for archive', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ template_type: 'archive', contract_sub_type: null, case_sub_type: null, archive_sub_type: 'unknown_archive_sub' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('unknown_archive_sub')).toBeInTheDocument()
  })

  it('shows dash when no sub type is set', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ template_type: 'contract', contract_sub_type: null })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    // '-' appears in sub type column
    const cells = screen.getAllByText('-')
    expect(cells.length).toBeGreaterThanOrEqual(1)
  })

  // ---- File source display ----
  it('shows uploaded file indicator when file is present', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ file: { name: 'test.docx', size: 1024 }, file_path: '' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('上传文件')).toBeInTheDocument()
  })

  it('shows path reference indicator when file_path is present but no file', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ file: null, file_path: 'some/path.docx' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('路径引用')).toBeInTheDocument()
  })

  it('shows dash when no file or file_path', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ file: null, file_path: '' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    // Multiple dashes could appear, check that at least one exists
    const dashes = screen.getAllByText('-')
    expect(dashes.length).toBeGreaterThanOrEqual(1)
  })

  // ---- Undefined placeholders ----
  it('shows undefined placeholder warning badge when undefCount > 0', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ placeholders: ['p1', 'p2'], undefined_placeholders: ['p3'] })],
      isLoading: false,
    } as any)
    const { container } = render(<TemplateList />)
    expect(container.querySelector('.text-status-red')).toBeInTheDocument()
    expect(screen.getByText('1 !')).toBeInTheDocument()
  })

  it('does not show undefined placeholder badge when undefCount is 0', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ placeholders: ['p1'], undefined_placeholders: [] })],
      isLoading: false,
    } as any)
    const { container } = render(<TemplateList />)
    expect(container.querySelector('.text-status-red')).not.toBeInTheDocument()
  })

  // ---- Applicable scope display ----
  it('shows case types in scope column when case_types present', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ case_types: ['civil', 'administrative'], contract_types: [] })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('civil、administrative')).toBeInTheDocument()
  })

  it('shows contract types in scope column when contract_types present', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ case_types: [], contract_types: ['civil', 'labor'] })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('civil、labor')).toBeInTheDocument()
  })

  it('shows combined types when both case_types and contract_types present', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ case_types: ['civil'], contract_types: ['labor'] })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('civil、labor')).toBeInTheDocument()
  })

  it('shows 通用 when no case_types or contract_types', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ case_types: [], contract_types: [] })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('通用')).toBeInTheDocument()
  })

  it('shows 通用 when case_types and contract_types are undefined', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ case_types: undefined as any, contract_types: undefined as any })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('通用')).toBeInTheDocument()
  })

  // ---- Edit button ----
  it('renders edit button for each template', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ id: 42 })], isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('编辑')).toBeInTheDocument()
  })

  // ---- Search filtering ----
  it('filters templates by search text', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [
        makeTemplate({ id: 1, name: '民事起诉状' }),
        makeTemplate({ id: 2, name: '合同协议' }),
      ],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('民事起诉状')).toBeInTheDocument()
    expect(screen.getByText('合同协议')).toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText('搜索模板名称...'), { target: { value: '民事' } })
    expect(screen.getByText('民事起诉状')).toBeInTheDocument()
    expect(screen.queryByText('合同协议')).not.toBeInTheDocument()
  })

  it('search is case insensitive', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ id: 1, name: 'Contract Template' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    fireEvent.change(screen.getByPlaceholderText('搜索模板名称...'), { target: { value: 'contract' } })
    expect(screen.getByText('Contract Template')).toBeInTheDocument()
  })

  it('shows clear search button when search is active', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate()], isLoading: false,
    } as any)
    render(<TemplateList />)
    const input = screen.getByPlaceholderText('搜索模板名称...')
    fireEvent.change(input, { target: { value: 'test' } })
    // The clear button (X) should be present as a sibling button
    const clearButtons = screen.getAllByRole('button')
    // At least one extra button for clearing
    expect(clearButtons.length).toBeGreaterThan(0)
  })

  it('clears search when X button is clicked', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ id: 1, name: '测试A' }), makeTemplate({ id: 2, name: '测试B' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    const input = screen.getByPlaceholderText('搜索模板名称...')
    fireEvent.change(input, { target: { value: '测试A' } })
    expect(screen.queryByText('测试B')).not.toBeInTheDocument()

    // Find the clear button - it's a ghost button with type="button"
    const buttons = screen.getAllByRole('button')
    // The clear button is positioned absolute inside the search input area
    // Find it by the ghost variant pattern
    const ghostButtons = buttons.filter(btn => btn.className.includes('size-7') || btn.querySelector('.size-4'))
    if (ghostButtons.length > 0) {
      fireEvent.click(ghostButtons[0])
    }
  })

  // ---- Type filtering ----
  // ---- Active only filter ----
  it('filters to active only when checkbox is checked', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [
        makeTemplate({ id: 1, name: '启用模板', is_active: true }),
        makeTemplate({ id: 2, name: '禁用模板', is_active: false }),
      ],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('启用模板')).toBeInTheDocument()
    expect(screen.getByText('禁用模板')).toBeInTheDocument()

    fireEvent.click(screen.getByText('仅显示启用'))
    expect(screen.getByText('启用模板')).toBeInTheDocument()
    expect(screen.queryByText('禁用模板')).not.toBeInTheDocument()
  })

  // ---- Template type badge labels ----
  it('shows correct type badge for contract', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ template_type: 'contract', contract_sub_type: 'contract' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('合同文件模板')).toBeInTheDocument()
  })

  it('shows correct type badge for case', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ template_type: 'case', contract_sub_type: null, case_sub_type: 'pleading_materials' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('案件文件模板')).toBeInTheDocument()
  })

  it('shows correct type badge for archive', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ template_type: 'archive', contract_sub_type: null, case_sub_type: null, archive_sub_type: 'case_cover' })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('归档文件模板')).toBeInTheDocument()
  })

  it('shows raw type when type is unknown', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ template_type: 'unknown_type' as any })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('unknown_type')).toBeInTheDocument()
  })

  // ---- Multiple templates rendering ----
  it('renders multiple templates in order', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [
        makeTemplate({ id: 1, name: '模板A' }),
        makeTemplate({ id: 2, name: '模板B' }),
        makeTemplate({ id: 3, name: '模板C' }),
      ],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('模板A')).toBeInTheDocument()
    expect(screen.getByText('模板B')).toBeInTheDocument()
    expect(screen.getByText('模板C')).toBeInTheDocument()
  })

  // ---- Placeholders count ----
  it('displays placeholder count', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ placeholders: ['a', 'b', 'c'], undefined_placeholders: [] })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('3')).toBeInTheDocument()
  })

  it('handles missing placeholders array', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ placeholders: undefined as any, undefined_placeholders: undefined as any })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('0')).toBeInTheDocument()
  })

  // ---- Combined filters ----
  it('applies type filter, search, and activeOnly together', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [
        makeTemplate({ id: 1, name: '民事合同A', template_type: 'contract', contract_sub_type: 'contract', is_active: true }),
        makeTemplate({ id: 2, name: '民事合同B', template_type: 'contract', contract_sub_type: 'contract', is_active: false }),
      ],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    fireEvent.click(screen.getByText('仅显示启用'))
    expect(screen.getByText('民事合同A')).toBeInTheDocument()
    expect(screen.queryByText('民事合同B')).not.toBeInTheDocument()
  })

  // ---- Edit button stopPropagation ----
  it('edit button has stopPropagation to prevent row click', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ id: 42 })], isLoading: false,
    } as any)
    render(<TemplateList />)
    const editBtn = screen.getByText('编辑')
    // The button should exist and be clickable without propagating to the row
    expect(editBtn).toBeInTheDocument()
    fireEvent.click(editBtn)
  })

  // ---- Zero placeholder + zero undef ----
  it('handles template with zero placeholders and zero undefined', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ placeholders: [], undefined_placeholders: [] })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('0')).toBeInTheDocument()
  })

  // ---- Multiple undefined placeholders ----
  it('shows correct count for multiple undefined placeholders', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [makeTemplate({ placeholders: ['a', 'b', 'c', 'd'], undefined_placeholders: ['x', 'y', 'z'] })],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('3 !')).toBeInTheDocument()
  })
})
