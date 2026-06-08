vi.mock('../../hooks/use-template-library-files', () => ({
  useTemplateLibraryFiles: () => ({ data: [] }),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_TEMPLATES: '/templates' },
}))

import { render, screen } from '@testing-library/react'
import { TemplateForm } from '../TemplateForm'

describe('TemplateForm', () => {
  it('renders step indicators', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getAllByText('适用范围').length).toBeGreaterThanOrEqual(1)
  })

  it('renders template name input', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getByPlaceholderText('例：民事起诉状（通用）')).toBeInTheDocument()
  })

  it('renders save button in create mode', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getByText('保存模板')).toBeInTheDocument()
  })

  it('renders save button in edit mode', () => {
    const template = { id: 1, name: 'Test', template_type: 'contract' as const, is_active: true, placeholders: [], undefined_placeholders: [], updated_at: '' }
    render(<TemplateForm template={template as any} onSubmit={vi.fn()} />)
    expect(screen.getByText('保存修改')).toBeInTheDocument()
  })

  it('renders cancel button', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getByText('取消')).toBeInTheDocument()
  })
})
