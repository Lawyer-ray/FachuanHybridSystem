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
  EmptyState: ({ title }: any) => <div>{title}</div>,
}))

import { render, screen } from '@testing-library/react'
import { TemplateList } from '../TemplateList'
import { useTemplates } from '../../hooks/use-templates'

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

  it('shows empty state when no templates', () => {
    vi.mocked(useTemplates).mockReturnValue({ data: [], isLoading: false } as any)
    render(<TemplateList />)
    expect(screen.getByText('没有匹配的模板')).toBeInTheDocument()
  })

  it('renders template data when available', () => {
    vi.mocked(useTemplates).mockReturnValue({
      data: [{
        id: 1, name: '民事起诉状', template_type: 'case', is_active: true,
        contract_sub_type: null, case_sub_type: 'pleading', archive_sub_type: null,
        file: null, file_path: 'case/pleading.docx', placeholders: ['原告', '被告'],
        undefined_placeholders: [], updated_at: '2026-06-01', case_types: ['civil'], contract_types: [],
        legal_statuses: [], legal_status_match_mode: 'any', applicable_institutions: [],
      }],
      isLoading: false,
    } as any)
    render(<TemplateList />)
    expect(screen.getByText('民事起诉状')).toBeInTheDocument()
  })
})
