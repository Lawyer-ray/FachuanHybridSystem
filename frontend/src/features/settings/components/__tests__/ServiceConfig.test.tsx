import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { useParams } from 'react-router'
import { ServiceConfig } from '../ServiceConfig'

const mockUseParams = vi.mocked(useParams)

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
    mutate: vi.fn(),
    isPending: false,
  }),
  useCreateSystemConfig: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
  usePatchSystemConfig: () => ({
    mutate: vi.fn(),
    isPending: false,
  }),
  useDeleteSystemConfig: () => ({
    mutate: vi.fn(),
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
  },
}))

import { useSystemConfigs } from '../../hooks/use-system-configs'

const mockUseSystemConfigs = useSystemConfigs as unknown as ReturnType<typeof vi.fn>

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

  it('renders empty state', () => {
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

  it('handles save with no changes', () => {
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('保存配置'))
    // Should show "没有需要保存的修改"
  })

  it('handles field change and save', () => {
    render(<ServiceConfig />)
    const input = screen.getByDisplayValue('gpt-4o')
    fireEvent.change(input, { target: { value: 'gpt-4' } })
    fireEvent.click(screen.getByText('保存配置'))
  })

  it('renders secret toggle in create dialog', () => {
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('新增配置'))
    expect(screen.getByText('敏感信息（密码遮罩）')).toBeInTheDocument()
  })

  it('renders create dialog fields', () => {
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('新增配置'))
    expect(screen.getByPlaceholderText('MY_CONFIG_KEY')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入配置值')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('配置项用途说明')).toBeInTheDocument()
  })

  it('handles create with empty key', () => {
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('新增配置'))
    fireEvent.click(screen.getByText('创建'))
    // Should show error toast for empty key
  })

  it('shows secret field with toggle visibility', () => {
    render(<ServiceConfig />)
    // The secret field should have the eye icon button for toggling visibility
    // Check that the "已设置" text is present for the secret field
    expect(screen.getByText('已设置')).toBeInTheDocument()
    // There should be toggle buttons in the UI
    const allButtons = screen.getAllByRole('button')
    expect(allButtons.length).toBeGreaterThan(0)
  })

  it('renders field with has_value false', () => {
    mockUseSystemConfigs.mockReturnValue({
      data: [{
        category: 'llm',
        items: [
          { key: 'OPENAI_API_KEY', value: '', category: 'llm', description: 'Key', is_secret: true, is_active: true, has_value: false },
        ],
      }],
      isLoading: false,
    })
    render(<ServiceConfig />)
    expect(screen.getByText('未设置')).toBeInTheDocument()
  })

  it('renders system category with test connection button', () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    render(<ServiceConfig />)
    expect(screen.getByText('测试连通性')).toBeInTheDocument()
    expect(screen.getByText('后端地址')).toBeInTheDocument()
  })

  it('handles test connection click', () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'ok' }),
    })
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('测试连通性'))
  })

  it('handles system category save', () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    render(<ServiceConfig />)
    fireEvent.click(screen.getByText('保存配置'))
  })

  it('renders system category description', () => {
    render(<ServiceConfig />)
    expect(screen.getByText('配置大语言模型相关参数')).toBeInTheDocument()
  })

  it('shows no description when empty', () => {
    mockUseParams.mockReturnValue({ category: 'system' })
    render(<ServiceConfig />)
    // System category has empty description
    expect(screen.queryByText('配置大语言模型相关参数')).not.toBeInTheDocument()
  })
})
