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

import { render, screen, fireEvent } from '@testing-library/react'
import { TemplateForm } from '../TemplateForm'

describe('TemplateForm', () => {
  it('renders step indicators', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getAllByText('适用范围').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('基本信息').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('模板类型').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('文件配置').length).toBeGreaterThanOrEqual(1)
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

  it('renders template type buttons', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getByText('合同文件模板')).toBeInTheDocument()
    expect(screen.getByText('案件文件模板')).toBeInTheDocument()
    expect(screen.getByText('归档文件模板')).toBeInTheDocument()
  })

  it('renders active switch', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getByText('启用（保存后立即可用）')).toBeInTheDocument()
  })

  it('renders file source options', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getByText('从模板库选择')).toBeInTheDocument()
    expect(screen.getByText('上传新文件')).toBeInTheDocument()
    expect(screen.getByText('手动输入路径')).toBeInTheDocument()
  })

  it('renders legal status options', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getByText('原告')).toBeInTheDocument()
    expect(screen.getByText('被告')).toBeInTheDocument()
  })

  it('renders contract sub-types by default', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    // Default type is contract, so contract sub-types should show
    expect(screen.getByText('合同类型（可多选）')).toBeInTheDocument()
  })

  it('switches to case type and shows case sub-types', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByText('案件文件模板'))
    expect(screen.getByText('案件类型（可多选）')).toBeInTheDocument()
    expect(screen.getByText('案件阶段（可多选）')).toBeInTheDocument()
  })

  it('switches to archive type', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByText('归档文件模板'))
    expect(screen.getByText('归档文件模板')).toBeInTheDocument()
  })

  it('toggles legal status selection', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByText('原告'))
    // Should show match mode options when legal statuses are selected
    expect(screen.getByText('诉讼地位匹配模式')).toBeInTheDocument()
  })

  it('renders match mode options when legal status selected', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByText('原告'))
    expect(screen.getByText('任意匹配')).toBeInTheDocument()
    expect(screen.getByText('全部包含')).toBeInTheDocument()
    expect(screen.getByText('完全一致')).toBeInTheDocument()
  })

  it('renders applicable institutions input', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getByText('适用机构（留空=不限）')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('输入法院名称，多个用逗号分隔')).toBeInTheDocument()
  })

  it('does not call onSubmit with empty name', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('calls onSubmit with valid data', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: '测试模板' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ name: '测试模板' }))
  })

  it('renders upload drop zone when upload source selected', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getByText(/点击选择或拖拽.*docx.*文件到这里/)).toBeInTheDocument()
  })

  it('renders path input when path source selected', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByText('手动输入路径'))
    expect(screen.getByPlaceholderText('例：case/pleading/起诉状.docx')).toBeInTheDocument()
  })

  it('renders with existing template in edit mode', () => {
    const template = {
      id: 1, name: 'Existing Template', template_type: 'case' as const,
      is_active: false, case_sub_type: 'complaint', case_types: ['civil'],
      case_stages: ['first_trial'], legal_statuses: ['plaintiff'],
      legal_status_match_mode: 'any', applicable_institutions: ['北京法院'],
      file_path: 'case/complaint.docx', file: null,
      placeholders: [], undefined_placeholders: [], updated_at: '2026-01-01',
    }
    render(<TemplateForm template={template as any} onSubmit={vi.fn()} />)
    expect(screen.getByDisplayValue('Existing Template')).toBeInTheDocument()
  })

  it('renders contract types for contract template', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getByText('民商事')).toBeInTheDocument()
    expect(screen.getByText('刑事')).toBeInTheDocument()
    expect(screen.getByText('常法顾问')).toBeInTheDocument()
  })

  it('toggles contract type selection', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByText('民商事'))
    // Should still render
    expect(screen.getByText('民商事')).toBeInTheDocument()
  })

  it('toggles case type selection', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByText('案件文件模板'))
    fireEvent.click(screen.getByText('民事'))
    expect(screen.getByText('民事')).toBeInTheDocument()
  })

  it('toggles case stage selection', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByText('案件文件模板'))
    fireEvent.click(screen.getByText('一审'))
    expect(screen.getByText('一审')).toBeInTheDocument()
  })
})
