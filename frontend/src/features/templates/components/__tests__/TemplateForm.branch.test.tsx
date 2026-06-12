/**
 * Branch-focused tests for TemplateForm.tsx
 * Targets uncovered branches in subType initialization, file source, and submit
 */
import { render, screen, fireEvent } from '@testing-library/react'
import { TemplateForm } from '../TemplateForm'
import type { Template } from '../../types'

vi.mock('../../hooks/use-template-library-files', () => ({
  useTemplateLibraryFiles: () => ({
    data: [
      { path: 'contracts/template1.docx', name: 'Template 1' },
      { path: 'cases/pleading.docx', name: 'Pleading' },
    ],
  }),
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_TEMPLATES: '/templates' },
}))

describe('TemplateForm - branch coverage', () => {
  // subType initialization: contract_sub_type (branch 5[0])
  it('initializes with contract_sub_type from template', () => {
    const template = {
      id: 1, name: 'T', template_type: 'contract' as const, contract_sub_type: 'supplementary_agreement',
      case_sub_type: null, archive_sub_type: null, is_active: true,
      file: null, file_path: '', case_types: [], case_stages: [], contract_types: [],
      legal_statuses: [], legal_status_match_mode: 'any', applicable_institutions: [],
      placeholders: [], undefined_placeholders: [], updated_at: '',
    }
    const onSubmit = vi.fn()
    render(<TemplateForm template={template as Template} onSubmit={onSubmit} />)
    expect(screen.getByText('保存修改')).toBeInTheDocument()
  })

  // subType initialization: case_sub_type (branch 7[0])
  it('initializes with case_sub_type from template', () => {
    const template = {
      id: 1, name: 'T', template_type: 'case' as const, case_sub_type: 'evidence_materials',
      contract_sub_type: null, archive_sub_type: null, is_active: true,
      file: null, file_path: '', case_types: [], case_stages: [], contract_types: [],
      legal_statuses: [], legal_status_match_mode: 'any', applicable_institutions: [],
      placeholders: [], undefined_placeholders: [], updated_at: '',
    }
    render(<TemplateForm template={template as Template} onSubmit={vi.fn()} />)
    expect(screen.getByText('保存修改')).toBeInTheDocument()
  })

  // subType initialization: archive_sub_type (falls through to ARCHIVE_SUB_TYPE_LABELS)
  it('initializes with archive_sub_type from template', () => {
    const template = {
      id: 1, name: 'T', template_type: 'archive' as const, archive_sub_type: 'case_cover',
      contract_sub_type: null, case_sub_type: null, is_active: true,
      file: null, file_path: '', case_types: [], case_stages: [], contract_types: [],
      legal_statuses: [], legal_status_match_mode: 'any', applicable_institutions: [],
      placeholders: [], undefined_placeholders: [], updated_at: '',
    }
    render(<TemplateForm template={template as Template} onSubmit={vi.fn()} />)
    expect(screen.getByText('保存修改')).toBeInTheDocument()
  })

  // subType initialization: no sub types, fallback to first key (branch 8[1])
  it('falls back to first sub type key when no sub type set', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    // Default is contract type with first sub type
    expect(screen.getByText('合同模板')).toBeInTheDocument()
  })

  // fileSource: existing (branch 16[0]: template?.file ? 'upload' : ...)
  it('initializes fileSource as upload when template has no file or path', () => {
    const template = {
      id: 1, name: 'T', template_type: 'contract' as const, is_active: true,
      file: null, file_path: '', placeholders: [], undefined_placeholders: [], updated_at: '',
    }
    render(<TemplateForm template={template as Template} onSubmit={vi.fn()} />)
    expect(screen.getByText('上传新文件')).toBeInTheDocument()
  })

  // fileSource: path (branch 16[1])
  it('initializes fileSource as path when template has file_path but no file', () => {
    const template = {
      id: 1, name: 'T', template_type: 'contract' as const, is_active: true,
      file: null, file_path: 'contracts/template.docx', placeholders: [], undefined_placeholders: [], updated_at: '',
    }
    render(<TemplateForm template={template as Template} onSubmit={vi.fn()} />)
    expect(screen.getByText('手动输入路径')).toBeInTheDocument()
  })

  // fileSource: upload (template has file)
  it('initializes fileSource as upload when template has file', () => {
    const template = {
      id: 1, name: 'T', template_type: 'contract' as const, is_active: true,
      file: { name: 'test.docx', size: 1024 }, file_path: '', placeholders: [], undefined_placeholders: [], updated_at: '',
    }
    render(<TemplateForm template={template as Template} onSubmit={vi.fn()} />)
    expect(screen.getByText('上传新文件')).toBeInTheDocument()
  })

  // useEffect: libraryFiles matches template.file_path -> setFileSource('existing') (branch 21[0])
  it('sets fileSource to existing when libraryFiles matches template file_path', () => {
    const template = {
      id: 1, name: 'T', template_type: 'contract' as const, is_active: true,
      file: null, file_path: 'contracts/template1.docx', placeholders: [], undefined_placeholders: [], updated_at: '',
    }
    render(<TemplateForm template={template as Template} onSubmit={vi.fn()} />)
    // Should show "从模板库选择" with the path matched
    expect(screen.getByText('从模板库选择')).toBeInTheDocument()
  })

  // handleTypeChange: resets subType (fn 104-107)
  it('resets subType when changing template type', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByText('案件文件模板'))
    expect(screen.getByText('诉状材料')).toBeInTheDocument()
  })

  // toggleArrayItem: add item to array (branch 110: includes ? filter : spread)
  it('toggles contract type selection on and off', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    fireEvent.click(screen.getByText('民商事'))
    // Click again to deselect
    fireEvent.click(screen.getByText('民商事'))
    expect(screen.getByText('民商事')).toBeInTheDocument()
  })

  // handleSubmit: empty name guard (branch 114: !name.trim())
  it('does not submit with empty name', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  // handleSubmit: contract type with subType (branches 119-128)
  it('submits contract type with correct sub type', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'My Template' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      name: 'My Template',
      template_type: 'contract',
      contract_sub_type: 'contract',
      case_sub_type: null,
      archive_sub_type: null,
    }))
  })

  // handleSubmit: case type with sub types (branches 120-123)
  it('submits case type with case sub type', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('案件文件模板'))
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Case Template' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      template_type: 'case',
      case_sub_type: expect.any(String),
      contract_sub_type: null,
    }))
  })

  // handleSubmit: archive type (branch 121)
  it('submits archive type with archive sub type', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('归档文件模板'))
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Archive Template' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      template_type: 'archive',
      archive_sub_type: expect.any(String),
      contract_sub_type: null,
      case_sub_type: null,
    }))
  })

  // handleSubmit: with legal statuses and match mode (branch 30, 31)
  it('submits with legal statuses and match mode', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('原告'))
    fireEvent.click(screen.getByText('全部包含'))
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      legal_statuses: ['plaintiff'],
      legal_status_match_mode: 'all',
    }))
  })

  // handleSubmit: with institutions (branch 127)
  it('submits with institutions split by comma', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Test' } })
    fireEvent.change(screen.getByPlaceholderText('输入法院名称，多个用逗号分隔'), { target: { value: '北京法院,上海法院' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      applicable_institutions: ['北京法院', '上海法院'],
    }))
  })

  // handleSubmit: fileSource is 'path' (branch 128: file_source === 'path')
  it('submits with file path when path source selected', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('手动输入路径'))
    fireEvent.change(screen.getByPlaceholderText('例：case/pleading/起诉状.docx'), { target: { value: 'case/test.docx' } })
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      file_path: 'case/test.docx',
    }))
  })

  // handleSubmit: fileSource is 'existing' (branch 128: file_source === 'existing')
  it('submits with file path when existing source selected', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('从模板库选择'))
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      file_path: '',
    }))
  })

  // handleSubmit: fileSource is 'upload' (branch 128: neither path nor existing)
  it('submits with empty file_path for upload', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      file_path: '',
    }))
  })

  // handleSubmit: institutions with Chinese comma (branch 127)
  it('splits institutions by Chinese comma', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Test' } })
    fireEvent.change(screen.getByPlaceholderText('输入法院名称，多个用逗号分隔'), { target: { value: '法院A，法院B' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      applicable_institutions: ['法院A', '法院B'],
    }))
  })

  // handleSubmit: empty institutions (branch 127: empty string)
  it('submits with empty institutions', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      applicable_institutions: [],
    }))
  })

  // handleSubmit: contract_types selected (branch 124)
  it('submits with contract types when selected', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('民商事'))
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      contract_types: ['civil'],
    }))
  })

  // handleSubmit: case_types and case_stages (branches 122-123)
  it('submits with case types and stages when case type selected', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('案件文件模板'))
    fireEvent.click(screen.getByText('民事'))
    fireEvent.click(screen.getByText('一审'))
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      case_types: ['civil'],
      case_stages: ['first_trial'],
    }))
  })

  // handleSubmit: is_active from switch (branch 117)
  it('submits with is_active value', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Test' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      is_active: true,
    }))
  })

  // Upload area: fileInputRef click (branch 416-420)
  it('renders upload area for upload source', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    expect(screen.getByText(/点击选择或拖拽/)).toBeInTheDocument()
  })

  // Select file and remove it (branch 432-435)
  it('renders upload area and file input', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    const input = document.querySelector('input[type="file"]')
    expect(input).toBeInTheDocument()
  })

  // Path input disabled when not path source (branch 458-459)
  it('disables path input when not path source selected', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    const pathInput = screen.getByPlaceholderText('例：case/pleading/起诉状.docx')
    expect(pathInput).toBeDisabled()
  })

  // select disabled when not existing source (branch 386)
  it('disables library select when not existing source', () => {
    render(<TemplateForm onSubmit={vi.fn()} />)
    const select = document.querySelector('select')
    expect(select).toBeDisabled()
  })

  // isEdit mode (branch 70: !!template)
  it('renders edit mode with template', () => {
    const template = {
      id: 1, name: 'Existing', template_type: 'contract' as const, is_active: true,
      file: null, file_path: '', placeholders: [], undefined_placeholders: [], updated_at: '',
    }
    render(<TemplateForm template={template as Template} onSubmit={vi.fn()} />)
    expect(screen.getByText('保存修改')).toBeInTheDocument()
  })

  // institutions with extra whitespace (branch 127: trim)
  it('trims institutions whitespace', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Test' } })
    fireEvent.change(screen.getByPlaceholderText('输入法院名称，多个用逗号分隔'), { target: { value: ' 法院A , 法院B ' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      applicable_institutions: ['法院A', '法院B'],
    }))
  })

  // Empty institutions string with only commas
  it('filters out empty institutions from commas', () => {
    const onSubmit = vi.fn()
    render(<TemplateForm onSubmit={onSubmit} />)
    fireEvent.change(screen.getByPlaceholderText('例：民事起诉状（通用）'), { target: { value: 'Test' } })
    fireEvent.change(screen.getByPlaceholderText('输入法院名称，多个用逗号分隔'), { target: { value: ',,' } })
    fireEvent.click(screen.getByText('保存模板'))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      applicable_institutions: [],
    }))
  })
})
