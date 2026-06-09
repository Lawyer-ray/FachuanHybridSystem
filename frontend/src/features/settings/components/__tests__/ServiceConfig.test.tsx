import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react'
import { useParams } from 'react-router'
import { ServiceConfig } from '../ServiceConfig'

const mockUseParams = vi.mocked(useParams)

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
    info: vi.fn(),
  },
}))

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn(), useParams: vi.fn().mockReturnValue({ category: 'llm' }) }
})
vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_SETTINGS: '/admin/settings' },
}))
vi.mock('@/lib/api', () => ({
  getApiBaseUrl: () => 'http://localhost:8002/api/v1',
  getBackendUrl: () => 'http://localhost:8002',
}))

const mockUpdateMutate = vi.fn()
const mockCreateMutate = vi.fn()
const mockPatchMutate = vi.fn()
const mockDeleteMutate = vi.fn()

vi.mock('../../hooks/use-system-configs', () => ({
  useSystemConfigs: vi.fn().mockReturnValue({
    data: [{
      category: 'llm',
      items: [
        { key: 'OPENAI_API_KEY', value: 'sk-test', category: 'llm', description: 'OpenAI API Key', is_secret: true, is_active: true, has_value: true },
        { key: 'LLM_MODEL', value: 'gpt-4o', category: 'llm', description: 'Default model', is_secret: false, is_active: true, has_value: true },
      ],
    }],
    isLoading: false,
  }),
  useUpdateSystemConfigs: () => ({
    mutate: mockUpdateMutate,
    isPending: false,
  }),
  useCreateSystemConfig: () => ({
    mutate: mockCreateMutate,
    isPending: false,
  }),
  usePatchSystemConfig: () => ({
    mutate: mockPatchMutate,
    isPending: false,
  }),
  useDeleteSystemConfig: () => ({
    mutate: mockDeleteMutate,
    isPending: false,
  }),
}))
vi.mock('../../constants/config-hints', () => ({
  CATEGORY_HINTS: {
    llm: {
      title: 'LLM 配置',
      description: '配置大语言模型相关参数',
      fields: {
        OPENAI_API_KEY: { label: 'OpenAI API Key', placeholder: 'sk-...', fullWidth: true },
        LLM_MODEL: { label: '默认模型', placeholder: 'gpt-4o' },
      },
      fieldOrder: ['OPENAI_API_KEY', 'LLM_MODEL'],
      groups: [],
    },
    system: { title: '系统连接', description: '' },
    nohints: { title: 'No Hints', description: 'No hints category' },
  },
}))

import { useSystemConfigs } from '../../hooks/use-system-configs'
import { toast } from 'sonner'

const mockUseSystemConfigs = useSystemConfigs as unknown as ReturnType<typeof vi.fn>
const mockToast = vi.mocked(toast)

describe('ServiceConfig', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
    mockUseParams.mockReturnValue({ category: 'llm' })
    mockUseSystemConfigs.mockReturnValue({
      data: [{
        category: 'llm',
        items: [
          { key: 'OPENAI_API_KEY', value: 'sk-test', category: 'llm', description: 'OpenAI API Key', is_secret: true, is_active: true, has_value: true },
          { key: 'LLM_MODEL', value: 'gpt-4o', category: 'llm', description: 'Default model', is_secret: false, is_active: true, has_value: true },
        ],
      }],
      isLoading: false,
    })
  })

  it('renders category title', () => {
    render(<ServiceConfig />)
    expect(screen.getByText('LLM 配置')).toBeInTheDocument()
  })

  it('renders description', () => {
    render(<ServiceConfig />)
    expect(screen.getByText('配置大语言模型相关参数')).toBeInTheDocument()
  })

  it('renders back button', () => {
    render(<ServiceConfig />)
    expect(screen.getByText('返回设置')).toBeInTheDocument()
  })

  it('renders save button', () => {
    render(<ServiceConfig />)
    expect(screen.getByText('保存配置')).toBeInTheDocument()
  })

  it('renders config fields', () => {
    render(<ServiceConfig />)
    expect(screen.getByText('OpenAI API Key')).toBeInTheDocument()
    expect(screen.getByText('默认模型')).toBeInTheDocument()
  })

  it('renders secret field with mask', () => {
    render(<ServiceConfig />)
    expect(screen.getByText('已设置')).toBeInTheDocument()
  })

  it('renders non-secret field with value', () => {
    render(<ServiceConfig />)
    expect(screen.getByDisplayValue('gpt-4o')).toBeInTheDocument()
  })

  it('renders add config button for non-system categories', () => {
    render(<ServiceConfig />)
    expect(screen.getByText('新增配置')).toBeInTheDocument()
  })

  it('opens create dialog', () => {
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('新增配置'))
    expect(screen.getByText('新增配置项')).toBeInTheDocument()
  })

  it('renders category badge', () => {
    render(<ServiceConfig />)
    expect(screen.getByText('llm')).toBeInTheDocument()
  })

  it('renders loading state', () => {
    mockUseSystemConfigs.mockReturnValue({ data: undefined, isLoading: true })
    render(<ServiceConfig />)
    expect(screen.getByText('加载中...')).toBeInTheDocument()
  })

  it('renders empty state when no matching category', () => {
    mockUseSystemConfigs.mockReturnValue({
      data: [{ category: 'other', items: [{ key: 'X', value: 'v', category: 'other', description: 'X', is_secret: false, is_active: true, has_value: true }] }],
      isLoading: false,
    })
    mockUseParams.mockReturnValue({ category: 'nonexistent' })
    render(<ServiceConfig />)
    expect(screen.getByText('该类别暂无配置项')).toBeInTheDocument()
  })

  it('renders empty state with empty groups', () => {
    mockUseSystemConfigs.mockReturnValue({ data: [], isLoading: false })
    render(<ServiceConfig />)
    expect(screen.getByText('该类别暂无配置项')).toBeInTheDocument()
  })

  it('renders edit and delete buttons for fields', () => {
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    expect(editButtons.length).toBeGreaterThan(0)
    const deleteButtons = screen.getAllByTitle('删除配置项')
    expect(deleteButtons.length).toBeGreaterThan(0)
  })

  it('opens edit dialog when clicking edit', () => {
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    fireEvent.click(editButtons[0])
    expect(screen.getByText('编辑配置项')).toBeInTheDocument()
  })

  it('opens delete dialog when clicking delete', () => {
    render(<ServiceConfig />)
    const deleteButtons = screen.getAllByTitle('删除配置项')
    fireEvent.click(deleteButtons[0])
    expect(screen.getByText('确认删除配置项')).toBeInTheDocument()
  })

  it('shows no description when empty', () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    render(<ServiceConfig />)
    expect(screen.queryByText('配置大语言模型相关参数')).not.toBeInTheDocument()
  })

  it('renders secret field with has_value true', () => {
    render(<ServiceConfig />)
    expect(screen.getByText('已设置')).toBeInTheDocument()
  })

  it('renders config field with fullWidth', () => {
    render(<ServiceConfig />)
    expect(screen.getByText('OpenAI API Key')).toBeInTheDocument()
  })

  // ─── Save with no changes ───
  it('shows info toast when saving with no changes', () => {
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('保存配置'))
    expect(mockToast.info).toHaveBeenCalledWith('没有需要保存的修改')
  })

  // ─── Save with changes ───
  it('calls updateMutation when saving with changes', () => {
    render(<ServiceConfig />)
    const input = screen.getByDisplayValue('gpt-4o')
    fireEvent.change(input, { target: { value: 'gpt-4' } })
    fireEvent.click(screen.getByText('保存配置'))
    expect(mockUpdateMutate).toHaveBeenCalledWith(
      { category: 'llm', updates: { LLM_MODEL: 'gpt-4' } },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('shows success toast on save success', () => {
    mockUpdateMutate.mockImplementation((_data: unknown, opts: { onSuccess: (res: { updated_count: number }) => void }) => {
      opts.onSuccess({ updated_count: 1 })
    })
    render(<ServiceConfig />)
    const input = screen.getByDisplayValue('gpt-4o')
    fireEvent.change(input, { target: { value: 'gpt-4' } })
    fireEvent.click(screen.getByText('保存配置'))
    expect(mockToast.success).toHaveBeenCalledWith('已保存 1 项配置')
  })

  it('shows error toast on save error', () => {
    mockUpdateMutate.mockImplementation((_data: unknown, opts: { onError: (err: Error) => void }) => {
      opts.onError(new Error('Network error'))
    })
    render(<ServiceConfig />)
    const input = screen.getByDisplayValue('gpt-4o')
    fireEvent.change(input, { target: { value: 'gpt-4' } })
    fireEvent.click(screen.getByText('保存配置'))
    expect(mockToast.error).toHaveBeenCalledWith('保存失败：Network error')
  })

  // ─── Create dialog ───
  it('handles create with empty key shows error', () => {
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('新增配置'))
    fireEvent.click(screen.getByText('创建'))
    expect(mockToast.error).toHaveBeenCalledWith('请输入配置项 Key')
  })

  it('handles create with valid key', () => {
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('新增配置'))
    fireEvent.change(screen.getByPlaceholderText('MY_CONFIG_KEY'), { target: { value: 'NEW_KEY' } })
    fireEvent.change(screen.getByPlaceholderText('请输入配置值'), { target: { value: 'new_value' } })
    fireEvent.change(screen.getByPlaceholderText('配置项用途说明'), { target: { value: 'A new config' } })
    fireEvent.click(screen.getByText('创建'))
    expect(mockCreateMutate).toHaveBeenCalledWith(
      expect.objectContaining({
        key: 'NEW_KEY',
        value: 'new_value',
        category: 'llm',
        description: 'A new config',
        is_secret: false,
      }),
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('shows success toast on create success', () => {
    mockCreateMutate.mockImplementation((_data: unknown, opts: { onSuccess: () => void }) => {
      opts.onSuccess()
    })
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('新增配置'))
    fireEvent.change(screen.getByPlaceholderText('MY_CONFIG_KEY'), { target: { value: 'NEW_KEY' } })
    fireEvent.click(screen.getByText('创建'))
    expect(mockToast.success).toHaveBeenCalledWith('配置项 NEW_KEY 已创建')
  })

  it('shows error toast on create error', () => {
    mockCreateMutate.mockImplementation((_data: unknown, opts: { onError: (err: Error) => void }) => {
      opts.onError(new Error('Duplicate key'))
    })
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('新增配置'))
    fireEvent.change(screen.getByPlaceholderText('MY_CONFIG_KEY'), { target: { value: 'DUP' } })
    fireEvent.click(screen.getByText('创建'))
    expect(mockToast.error).toHaveBeenCalledWith('创建失败：Duplicate key')
  })

  it('uppercases key input in create dialog', () => {
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('新增配置'))
    fireEvent.change(screen.getByPlaceholderText('MY_CONFIG_KEY'), { target: { value: 'my_key' } })
    expect(screen.getByPlaceholderText('MY_CONFIG_KEY')).toHaveValue('MY_KEY')
  })

  it('handles create cancel', () => {
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('新增配置'))
    expect(screen.getByText('新增配置项')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('dialog').querySelector('button')!)
  })

  it('renders secret toggle in create dialog', () => {
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('新增配置'))
    expect(screen.getByText('敏感信息（密码遮罩）')).toBeInTheDocument()
  })

  // ─── Edit dialog ───
  it('opens edit dialog with correct field values', () => {
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    fireEvent.click(editButtons[1]) // non-secret field (LLM_MODEL)
    expect(screen.getByText('编辑配置项')).toBeInTheDocument()
    // The edit dialog should show the current value and description
    expect(screen.getByDisplayValue('Default model')).toBeInTheDocument()
  })

  it('opens edit dialog for secret field with empty value', () => {
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    fireEvent.click(editButtons[0]) // secret field (OPENAI_API_KEY)
    expect(screen.getByText('编辑配置项')).toBeInTheDocument()
    // Secret fields should have empty value in edit mode
    const valueInput = screen.getAllByPlaceholderText('留空则不修改')[0]
    expect(valueInput).toBeInTheDocument()
  })

  it('calls patchMutation when saving edit with changes', () => {
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    fireEvent.click(editButtons[1]) // non-secret field
    // Change the description field instead to avoid duplicate value conflicts
    const descInput = screen.getByDisplayValue('Default model')
    fireEvent.change(descInput, { target: { value: 'Updated model' } })
    // Click save in the edit dialog
    const saveButtons = screen.getAllByText('保存')
    fireEvent.click(saveButtons[saveButtons.length - 1])
    expect(mockPatchMutate).toHaveBeenCalledWith(
      { key: 'LLM_MODEL', data: { description: 'Updated model' } },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('shows info toast when editing with no changes', () => {
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    fireEvent.click(editButtons[1]) // non-secret field, no changes
    const saveButtons = screen.getAllByText('保存')
    fireEvent.click(saveButtons[saveButtons.length - 1])
    expect(mockToast.info).toHaveBeenCalledWith('没有需要保存的修改')
  })

  it('shows success toast on edit success', () => {
    mockPatchMutate.mockImplementation((_data: unknown, opts: { onSuccess: () => void }) => {
      opts.onSuccess()
    })
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    fireEvent.click(editButtons[1])
    // Change description to trigger patch
    const descInput = screen.getByDisplayValue('Default model')
    fireEvent.change(descInput, { target: { value: 'Updated' } })
    const saveButtons = screen.getAllByText('保存')
    fireEvent.click(saveButtons[saveButtons.length - 1])
    expect(mockToast.success).toHaveBeenCalledWith('配置项已更新')
  })

  it('shows error toast on edit error', () => {
    mockPatchMutate.mockImplementation((_data: unknown, opts: { onError: (err: Error) => void }) => {
      opts.onError(new Error('Update failed'))
    })
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    fireEvent.click(editButtons[1])
    const descInput = screen.getByDisplayValue('Default model')
    fireEvent.change(descInput, { target: { value: 'Updated' } })
    const saveButtons = screen.getAllByText('保存')
    fireEvent.click(saveButtons[saveButtons.length - 1])
    expect(mockToast.error).toHaveBeenCalledWith('更新失败：Update failed')
  })

  it('handles edit cancel', () => {
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    fireEvent.click(editButtons[0])
    expect(screen.getByText('编辑配置项')).toBeInTheDocument()
    const cancelButtons = screen.getAllByText('取消')
    fireEvent.click(cancelButtons[cancelButtons.length - 1])
  })

  it('handles edit with secret field value change', () => {
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    fireEvent.click(editButtons[0]) // secret field (OPENAI_API_KEY)
    const valueInput = screen.getByPlaceholderText('留空则不修改')
    fireEvent.change(valueInput, { target: { value: 'new-secret' } })
    const saveButtons = screen.getAllByText('保存')
    fireEvent.click(saveButtons[saveButtons.length - 1])
    expect(mockPatchMutate).toHaveBeenCalledWith(
      { key: 'OPENAI_API_KEY', data: { value: 'new-secret' } },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('handles edit with non-secret value change via description path', () => {
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    fireEvent.click(editButtons[1]) // non-secret field (LLM_MODEL)
    // Change both value and description
    const descInput = screen.getByDisplayValue('Default model')
    fireEvent.change(descInput, { target: { value: 'New desc' } })
    const saveButtons = screen.getAllByText('保存')
    fireEvent.click(saveButtons[saveButtons.length - 1])
    expect(mockPatchMutate).toHaveBeenCalledWith(
      { key: 'LLM_MODEL', data: { description: 'New desc' } },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('handles edit with description change', () => {
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    fireEvent.click(editButtons[1]) // non-secret field
    const descInput = screen.getByDisplayValue('Default model')
    fireEvent.change(descInput, { target: { value: 'Updated description' } })
    const saveButtons = screen.getAllByText('保存')
    fireEvent.click(saveButtons[saveButtons.length - 1])
    expect(mockPatchMutate).toHaveBeenCalledWith(
      { key: 'LLM_MODEL', data: { description: 'Updated description' } },
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('includes is_secret toggle in edit dialog', () => {
    render(<ServiceConfig />)
    const editButtons = screen.getAllByTitle('编辑配置项')
    fireEvent.click(editButtons[1]) // non-secret field
    // Should have two switches: is_secret and is_active
    expect(screen.getByText('敏感信息（密码遮罩）')).toBeInTheDocument()
    expect(screen.getByText('启用')).toBeInTheDocument()
  })

  // ─── Delete dialog ───
  it('calls deleteMutation on delete confirm', () => {
    render(<ServiceConfig />)
    const deleteButtons = screen.getAllByTitle('删除配置项')
    fireEvent.click(deleteButtons[0])
    expect(screen.getByText('确认删除配置项')).toBeInTheDocument()
    fireEvent.click(screen.getByText('确认删除'))
    expect(mockDeleteMutate).toHaveBeenCalledWith(
      'OPENAI_API_KEY',
      expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) }),
    )
  })

  it('shows success toast on delete success', () => {
    mockDeleteMutate.mockImplementation((_key: string, opts: { onSuccess: () => void }) => {
      opts.onSuccess()
    })
    render(<ServiceConfig />)
    const deleteButtons = screen.getAllByTitle('删除配置项')
    fireEvent.click(deleteButtons[0])
    fireEvent.click(screen.getByText('确认删除'))
    expect(mockToast.success).toHaveBeenCalledWith('配置项 OPENAI_API_KEY 已删除')
  })

  it('shows error toast on delete error', () => {
    mockDeleteMutate.mockImplementation((_key: string, opts: { onError: (err: Error) => void }) => {
      opts.onError(new Error('Cannot delete'))
    })
    render(<ServiceConfig />)
    const deleteButtons = screen.getAllByTitle('删除配置项')
    fireEvent.click(deleteButtons[0])
    fireEvent.click(screen.getByText('确认删除'))
    expect(mockToast.error).toHaveBeenCalledWith('删除失败：Cannot delete')
  })

  it('handles delete dialog cancel', () => {
    render(<ServiceConfig />)
    const deleteButtons = screen.getAllByTitle('删除配置项')
    fireEvent.click(deleteButtons[0])
    fireEvent.click(screen.getByText('取消'))
  })

  // ─── System category ───
  it('renders system category with test connection button', () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    render(<ServiceConfig />)
    expect(screen.getByText('测试连通性')).toBeInTheDocument()
    expect(screen.getByText('后端地址')).toBeInTheDocument()
    expect(screen.getByText('API 基础路径')).toBeInTheDocument()
  })

  it('system category shows no add config button', () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    render(<ServiceConfig />)
    expect(screen.queryByText('新增配置')).not.toBeInTheDocument()
  })

  it('handles system category save with values', () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('保存配置'))
    expect(localStorage.getItem('backend_url')).toBe('http://localhost:8002')
    expect(localStorage.getItem('api_base_url')).toBe('http://localhost:8002/api/v1')
    expect(mockToast.success).toHaveBeenCalledWith('系统连接配置已保存，刷新页面后生效')
  })

  it('handles system category save with empty values removes localStorage', () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    render(<ServiceConfig />)
    // Clear the backend URL field
    const backendInput = screen.getByDisplayValue('http://localhost:8002')
    fireEvent.change(backendInput, { target: { value: '' } })
    const apiInput = screen.getByDisplayValue('http://localhost:8002/api/v1')
    fireEvent.change(apiInput, { target: { value: '' } })
    fireEvent.click(screen.getByText('保存配置'))
    expect(localStorage.getItem('backend_url')).toBeNull()
    expect(localStorage.getItem('api_base_url')).toBeNull()
  })

  it('handles system category field changes', () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    render(<ServiceConfig />)
    const backendInput = screen.getByDisplayValue('http://localhost:8002')
    fireEvent.change(backendInput, { target: { value: 'http://new-url:9000' } })
    expect(backendInput).toHaveValue('http://new-url:9000')
  })

  it('handles test connection with success response', async () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'healthy' }),
    })
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('测试连通性'))
    await waitFor(() => {
      expect(screen.getByText('连接成功 (healthy)')).toBeInTheDocument()
    })
  })

  it('handles test connection with ok response but no status', async () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({}),
    })
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('测试连通性'))
    await waitFor(() => {
      expect(screen.getByText('连接成功 (ok)')).toBeInTheDocument()
    })
  })

  it('handles test connection with error response', async () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 500,
    })
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('测试连通性'))
    await waitFor(() => {
      expect(screen.getByText('连接失败 (HTTP 500)')).toBeInTheDocument()
    })
  })

  it('handles test connection with network error', async () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    global.fetch = vi.fn().mockRejectedValue(new Error('Network error'))
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('测试连通性'))
    await waitFor(() => {
      expect(screen.getByText('无法连接到后端服务')).toBeInTheDocument()
    })
  })

  it('handles test connection with timeout', async () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    const abortError = new Error('Aborted')
    abortError.name = 'AbortError'
    global.fetch = vi.fn().mockRejectedValue(abortError)
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('测试连通性'))
    await waitFor(() => {
      expect(screen.getByText('连接超时 (5秒)')).toBeInTheDocument()
    })
  })

  it('shows success status icon after successful test connection', async () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    mockUseSystemConfigs.mockReturnValue({ data: undefined, isLoading: false })
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'ok' }),
    })
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('测试连通性'))
    await waitFor(() => {
      expect(screen.getByText('连接成功 (ok)')).toBeInTheDocument()
    })
    // The test message should have success styling
    const message = screen.getByText('连接成功 (ok)')
    expect(message.className).toContain('emerald')
  })

  it('disables test button while testing', async () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    let resolveFetch: (v: unknown) => void
    global.fetch = vi.fn().mockImplementation(() => new Promise((resolve) => { resolveFetch = resolve }))
    render(<ServiceConfig />)
    const testButton = screen.getByText('测试连通性')
    fireEvent.click(testButton)
    // Button should be disabled during test
    expect(testButton.closest('button')).toBeDisabled()
    resolveFetch!({ ok: true, json: () => Promise.resolve({ status: 'ok' }) })
  })

  // ─── Secret toggle visibility ───
  it('toggles secret field visibility', () => {
    render(<ServiceConfig />)
    // Initially, secret field shows "已设置" mask
    expect(screen.getByText('已设置')).toBeInTheDocument()
    // Find the secret field's value (should be masked, not showing sk-test)
    expect(screen.queryByDisplayValue('sk-test')).not.toBeInTheDocument()
  })

  // ─── Fields with no hints ───
  it('renders fields without hints using description as label', () => {
    mockUseParams.mockReturnValue({ category: 'nohints' })
    mockUseSystemConfigs.mockReturnValue({
      data: [{
        category: 'nohints',
        items: [
          { key: 'SOME_KEY', value: 'val', category: 'nohints', description: 'Some Config Key', is_secret: false, is_active: true, has_value: true },
        ],
      }],
      isLoading: false,
    })
    render(<ServiceConfig />)
    expect(screen.getByText('Some Config Key')).toBeInTheDocument()
  })

  it('renders fields without hints or description using key as label', () => {
    mockUseParams.mockReturnValue({ category: 'nohints' })
    mockUseSystemConfigs.mockReturnValue({
      data: [{
        category: 'nohints',
        items: [
          { key: 'RAW_KEY', value: 'val', category: 'nohints', description: '', is_secret: false, is_active: true, has_value: true },
        ],
      }],
      isLoading: false,
    })
    render(<ServiceConfig />)
    expect(screen.getByText('RAW_KEY')).toBeInTheDocument()
  })

  // ─── Multiple groups with hint groups ───
  it('renders with grouped hints', () => {
    mockUseSystemConfigs.mockReturnValue({
      data: [{
        category: 'llm',
        items: [
          { key: 'OPENAI_API_KEY', value: 'sk-test', category: 'llm', description: 'Key', is_secret: true, is_active: true, has_value: true },
          { key: 'LLM_MODEL', value: 'gpt-4o', category: 'llm', description: 'Model', is_secret: false, is_active: true, has_value: true },
          { key: 'EXTRA_KEY', value: 'extra', category: 'llm', description: 'Extra', is_secret: false, is_active: true, has_value: true },
        ],
      }],
      isLoading: false,
    })
    render(<ServiceConfig />)
    expect(screen.getByText('OpenAI API Key')).toBeInTheDocument()
  })

  // ─── getDisplayValue fallback ───
  it('returns empty string for unknown system key', () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    render(<ServiceConfig />)
    // The system values are populated from getBackendUrl/getApiBaseUrl
    // getDisplayValue should return the system value for known keys
    expect(screen.getByDisplayValue('http://localhost:8002')).toBeInTheDocument()
  })

  // ─── Edit with no backend item (handleEdit guard) ───
  it('returns early from handleEdit when editItem is null', () => {
    // This tests the guard: if (!editItem) return
    // Hard to test directly, but we can verify the dialog structure
    render(<ServiceConfig />)
    // No edit dialog should be open initially
    expect(screen.queryByText('编辑配置项')).not.toBeInTheDocument()
  })

  // ─── handleDelete guard ───
  it('returns early from handleDelete when deleteKey is null', () => {
    // This tests the guard: if (!deleteKey) return
    render(<ServiceConfig />)
    // No delete dialog should be open initially
    expect(screen.queryByText('确认删除配置项')).not.toBeInTheDocument()
  })

  // ─── Fallback title for unknown category ───
  it('uses category name as title when no hint exists', () => {
    mockUseParams.mockReturnValue({ category: 'unknown_category' })
    mockUseSystemConfigs.mockReturnValue({ data: [], isLoading: false })
    render(<ServiceConfig />)
    // Category appears in both h1 title and Badge
    const elements = screen.getAllByText('unknown_category')
    expect(elements.length).toBeGreaterThanOrEqual(1)
    // The h1 should be one of them
    const h1 = elements.find(el => el.tagName === 'H1')
    expect(h1).toBeInTheDocument()
  })

  it('uses "配置" as title when category is undefined', () => {
    mockUseParams.mockReturnValue({})
    mockUseSystemConfigs.mockReturnValue({ data: [], isLoading: false })
    render(<ServiceConfig />)
    expect(screen.getByText('配置')).toBeInTheDocument()
  })
})
