import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import TemplateListPage from '../TemplateListPage'
import TemplateNewPage from '../TemplateNewPage'
import TemplateEditPage from '../TemplateEditPage'

// Mock feature components
vi.mock('@/features/templates', () => ({
  TemplateList: () => <div data-testid="template-list">TemplateList</div>,
  TemplateForm: ({ template, onSubmit }: { template?: { name: string }; onSubmit: (data: unknown) => void }) => (
    <div data-testid="template-form">
      TemplateForm{template ? `-${template.name}` : ''}
      <button onClick={() => onSubmit({})}>Submit</button>
    </div>
  ),
}))

vi.mock('@/features/templates/hooks/use-template', () => ({
  useTemplate: vi.fn(),
}))

vi.mock('@/features/templates/hooks/use-template-mutations', () => ({
  useTemplateMutations: vi.fn().mockReturnValue({
    create: { mutate: vi.fn() },
    update: { mutate: vi.fn() },
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}))

vi.mock('lucide-react', () => ({
  ArrowLeft: (props: Record<string, unknown>) => <svg data-testid="arrow-left" {...props} />,
  FileWarning: (props: Record<string, unknown>) => <svg data-testid="file-warning" {...props} />,
}))

import { useTemplate } from '@/features/templates/hooks/use-template'
const mockUseTemplate = vi.mocked(useTemplate)

describe('TemplateListPage', () => {
  it('renders TemplateList component', () => {
    render(
      <MemoryRouter>
        <TemplateListPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('template-list')).toBeInTheDocument()
  })
})

describe('TemplateNewPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders page title', () => {
    render(
      <MemoryRouter>
        <TemplateNewPage />
      </MemoryRouter>,
    )

    expect(screen.getByText('新建文件模板')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(
      <MemoryRouter>
        <TemplateNewPage />
      </MemoryRouter>,
    )

    expect(screen.getByText(/创建新的法律文书模板/)).toBeInTheDocument()
  })

  it('renders TemplateForm component', () => {
    render(
      <MemoryRouter>
        <TemplateNewPage />
      </MemoryRouter>,
    )

    expect(screen.getByTestId('template-form')).toBeInTheDocument()
  })
})

describe('TemplateEditPage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading state', () => {
    mockUseTemplate.mockReturnValue({
      data: undefined,
      isLoading: true,
      error: null,
    } as ReturnType<typeof useTemplate>)

    render(
      <MemoryRouter initialEntries={['/admin/templates/1/edit']}>
        <Routes>
          <Route path="/admin/templates/:id/edit" element={<TemplateEditPage />} />
        </Routes>
      </MemoryRouter>,
    )

    // Shows loading skeleton
    expect(screen.queryByText('编辑文件模板')).not.toBeInTheDocument()
  })

  it('renders error state when template not found', () => {
    mockUseTemplate.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Not found'),
    } as ReturnType<typeof useTemplate>)

    render(
      <MemoryRouter initialEntries={['/admin/templates/999/edit']}>
        <Routes>
          <Route path="/admin/templates/:id/edit" element={<TemplateEditPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('模板不存在')).toBeInTheDocument()
  })

  it('renders edit form when template is loaded', () => {
    mockUseTemplate.mockReturnValue({
      data: { id: 1, name: '起诉状模板' },
      isLoading: false,
      error: null,
    } as ReturnType<typeof useTemplate>)

    render(
      <MemoryRouter initialEntries={['/admin/templates/1/edit']}>
        <Routes>
          <Route path="/admin/templates/:id/edit" element={<TemplateEditPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('编辑文件模板')).toBeInTheDocument()
    expect(screen.getByText(/修改模板/)).toBeInTheDocument()
    expect(screen.getByTestId('template-form')).toBeInTheDocument()
  })

  it('shows return button in error state', () => {
    mockUseTemplate.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error('Not found'),
    } as ReturnType<typeof useTemplate>)

    render(
      <MemoryRouter initialEntries={['/admin/templates/999/edit']}>
        <Routes>
          <Route path="/admin/templates/:id/edit" element={<TemplateEditPage />} />
        </Routes>
      </MemoryRouter>,
    )

    expect(screen.getByText('返回列表')).toBeInTheDocument()
  })
})
