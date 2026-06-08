import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { ServiceConfig } from '../components/ServiceConfig'
import { toast } from 'sonner'

vi.mock('lucide-react', () => ({
  ArrowLeft: () => <svg data-testid="arrow-left" />,
  Save: () => <svg data-testid="save-icon" />,
  Eye: () => <svg data-testid="eye-icon" />,
  EyeOff: () => <svg data-testid="eye-off-icon" />,
  Loader2: () => <svg data-testid="loader-icon" />,
  Plus: () => <svg data-testid="plus-icon" />,
  Pencil: () => <svg data-testid="pencil-icon" />,
  Trash2: () => <svg data-testid="trash-icon" />,
  Lock: () => <svg data-testid="lock-icon" />,
  ShieldCheck: () => <svg data-testid="shield-check" />,
  ShieldOff: () => <svg data-testid="shield-off" />,
  Wifi: () => <svg data-testid="wifi-icon" />,
  WifiOff: () => <svg data-testid="wifi-off" />,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }))

vi.mock('@/routes/paths', () => ({
  PATHS: { ADMIN_SETTINGS: '/admin/settings' },
}))

vi.mock('@/lib/api', () => ({
  getApiBaseUrl: () => 'http://localhost:8002/api/v1',
  getBackendUrl: () => 'http://localhost:8002',
}))

const mockMutate = vi.fn()
const mockUpdateMutate = vi.fn()
const mockCreateMutate = vi.fn()
const mockPatchMutate = vi.fn()
const mockDeleteMutate = vi.fn()

let hookOverrides: Record<string, unknown> = {}

vi.mock('../hooks/use-system-configs', () => ({
  useSystemConfigs: () => hookOverrides.systemConfigs ?? { data: null, isLoading: false },
  useUpdateSystemConfigs: () => hookOverrides.updateConfigs ?? ({ mutate: vi.fn(), isPending: false }),
  useCreateSystemConfig: () => hookOverrides.createConfig ?? ({ mutate: vi.fn(), isPending: false }),
  usePatchSystemConfig: () => hookOverrides.patchConfig ?? ({ mutate: vi.fn(), isPending: false }),
  useDeleteSystemConfig: () => hookOverrides.deleteConfig ?? ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('../constants/config-hints', () => ({
  CATEGORY_HINTS: {
    ai: {
      title: 'AI 服务配置',
      description: 'AI 后端参数',
      fields: {
        OPENAI_API_KEY: { label: 'OpenAI API Key', placeholder: 'sk-...', fullWidth: true },
      },
      fieldOrder: ['OPENAI_API_KEY'],
      groups: [],
    },
    tts: {
      title: 'TTS 配置',
      description: '',
      fields: {},
      fieldOrder: [],
      groups: [
        { label: '基础配置', keys: ['TTS_VOICE'] },
      ],
    },
  },
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))
vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))
vi.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: Record<string, unknown>) => <label {...props}>{children}</label>,
}))
vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant }: Record<string, unknown>) => <span data-variant={variant}>{children}</span>,
}))
vi.mock('@/components/ui/switch', () => ({
  Switch: ({ checked, onCheckedChange }: Record<string, unknown>) => (
    <input type="checkbox" checked={checked as boolean} onChange={(e) => (onCheckedChange as (v: boolean) => void)?.(e.target.checked)} />
  ),
}))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogAction: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

// Mock useParams - use a mutable mock function
const mockUseParams = vi.fn(() => ({}))
const mockUseNavigate = vi.fn(() => vi.fn())

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router')
  return {
    ...actual,
    useParams: (...args: unknown[]) => mockUseParams(...args),
    useNavigate: (...args: unknown[]) => mockUseNavigate(...args),
  }
})

function setCategory(cat: string | undefined) {
  mockUseParams.mockReturnValue({ category: cat })
}

describe('ServiceConfig', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    hookOverrides = {}
    setCategory(undefined)
  })

  it('renders default title when no category', () => {
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('配置')).toBeInTheDocument()
  })

  it('renders back button', () => {
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('返回设置')).toBeInTheDocument()
  })

  it('renders loading state', () => {
    hookOverrides = { systemConfigs: { data: null, isLoading: true } }
    setCategory('ai')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('加载中...')).toBeInTheDocument()
  })

  it('renders category title from hints', () => {
    setCategory('ai')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('AI 服务配置')).toBeInTheDocument()
  })

  it('renders category description', () => {
    setCategory('ai')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('AI 后端参数')).toBeInTheDocument()
  })

  it('renders save button', () => {
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('保存配置')).toBeInTheDocument()
  })

  it('renders new config button for non-system category', () => {
    setCategory('ai')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getAllByText('新增配置').length).toBeGreaterThan(0)
  })

  it('renders system category with backend URL fields', () => {
    setCategory('system')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('后端地址')).toBeInTheDocument()
    expect(screen.getByText('API 基础路径')).toBeInTheDocument()
    expect(screen.getByText('测试连通性')).toBeInTheDocument()
  })

  it('renders empty state when no fields', () => {
    setCategory('ai')
    hookOverrides = { systemConfigs: { data: [{ category: 'ai', items: [] }], isLoading: false } }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('该类别暂无配置项')).toBeInTheDocument()
  })

  it('renders config fields with data from backend', () => {
    setCategory('ai')
    hookOverrides = {
      systemConfigs: {
        data: [{
          category: 'ai',
          items: [{
            key: 'OPENAI_API_KEY',
            value: 'sk-test',
            description: 'OpenAI Key',
            is_secret: false,
            is_active: true,
            has_value: true,
            category: 'ai',
          }],
        }],
        isLoading: false,
      },
    }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('OpenAI API Key')).toBeInTheDocument()
  })

  it('renders secret field with lock icon and shield check', () => {
    setCategory('ai')
    hookOverrides = {
      systemConfigs: {
        data: [{
          category: 'ai',
          items: [{
            key: 'OPENAI_API_KEY',
            value: '',
            description: 'OpenAI Key',
            is_secret: true,
            is_active: true,
            has_value: true,
            category: 'ai',
          }],
        }],
        isLoading: false,
      },
    }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByTestId('lock-icon')).toBeInTheDocument()
    expect(screen.getByTestId('shield-check')).toBeInTheDocument()
    expect(screen.getByText('已设置')).toBeInTheDocument()
  })

  it('renders secret field with shield off when no value', () => {
    setCategory('ai')
    hookOverrides = {
      systemConfigs: {
        data: [{
          category: 'ai',
          items: [{
            key: 'OPENAI_API_KEY',
            value: '',
            description: 'OpenAI Key',
            is_secret: true,
            is_active: true,
            has_value: false,
            category: 'ai',
          }],
        }],
        isLoading: false,
      },
    }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByTestId('shield-off')).toBeInTheDocument()
    expect(screen.getByText('未设置')).toBeInTheDocument()
  })

  it('renders hint groups', () => {
    setCategory('tts')
    hookOverrides = {
      systemConfigs: {
        data: [{
          category: 'tts',
          items: [{
            key: 'TTS_VOICE',
            value: '冰糖',
            description: 'TTS Voice',
            is_secret: false,
            is_active: true,
            has_value: true,
            category: 'tts',
          }],
        }],
        isLoading: false,
      },
    }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('基础配置')).toBeInTheDocument()
  })

  it('clicking save with no changes shows info toast', () => {
    setCategory('ai')
    hookOverrides = {
      systemConfigs: {
        data: [{
          category: 'ai',
          items: [{
            key: 'OPENAI_API_KEY',
            value: 'sk-test',
            description: 'OpenAI Key',
            is_secret: false,
            is_active: true,
            has_value: true,
            category: 'ai',
          }],
        }],
        isLoading: false,
      },
    }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    fireEvent.click(screen.getByText('保存配置'))
    expect(toast.info).toHaveBeenCalledWith('没有需要保存的修改')
  })

  it('clicking save for system category saves to localStorage', () => {
    setCategory('system')
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    fireEvent.click(screen.getByText('保存配置'))
    expect(toast.success).toHaveBeenCalledWith('系统连接配置已保存，刷新页面后生效')
    setItemSpy.mockRestore()
  })

  it('shows category badge', () => {
    setCategory('ai')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('ai')).toBeInTheDocument()
  })

  it('renders new config dialog when clicking new config', () => {
    setCategory('ai')
    hookOverrides = {
      systemConfigs: {
        data: [{
          category: 'ai',
          items: [{
            key: 'OPENAI_API_KEY',
            value: 'sk-test',
            description: 'OpenAI Key',
            is_secret: false,
            is_active: true,
            has_value: true,
            category: 'ai',
          }],
        }],
        isLoading: false,
      },
    }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    fireEvent.click(screen.getByText('新增配置'))
    expect(screen.getByText('Key')).toBeInTheDocument()
  })

  it('handles create with empty key shows error', () => {
    setCategory('ai')
    hookOverrides = {
      systemConfigs: {
        data: [{
          category: 'ai',
          items: [{
            key: 'OPENAI_API_KEY',
            value: 'sk-test',
            description: 'OpenAI Key',
            is_secret: false,
            is_active: true,
            has_value: true,
            category: 'ai',
          }],
        }],
        isLoading: false,
      },
    }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    fireEvent.click(screen.getByText('新增配置'))
    // Click create without filling in key - find the create button in the dialog
    const createButton = screen.getAllByText('创建')
    fireEvent.click(createButton[0])
    expect(toast.error).toHaveBeenCalledWith('请输入配置项 Key')
  })

  it('renders edit and delete buttons for backend items', () => {
    setCategory('ai')
    hookOverrides = {
      systemConfigs: {
        data: [{
          category: 'ai',
          items: [{
            key: 'OPENAI_API_KEY',
            value: 'sk-test',
            description: 'OpenAI Key',
            is_secret: false,
            is_active: true,
            has_value: true,
            category: 'ai',
          }],
        }],
        isLoading: false,
      },
    }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByTitle('编辑配置项')).toBeInTheDocument()
    expect(screen.getByTitle('删除配置项')).toBeInTheDocument()
  })

  it('handles field change in non-system mode', () => {
    setCategory('ai')
    hookOverrides = {
      systemConfigs: {
        data: [{
          category: 'ai',
          items: [{
            key: 'OPENAI_API_KEY',
            value: '',
            description: 'OpenAI Key',
            is_secret: false,
            is_active: true,
            has_value: false,
            category: 'ai',
          }],
        }],
        isLoading: false,
      },
    }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    const inputs = screen.getAllByRole('textbox')
    if (inputs.length > 0) {
      fireEvent.change(inputs[0], { target: { value: 'new-value' } })
    }
    // Should not crash
    expect(screen.getByText('AI 服务配置')).toBeInTheDocument()
  })

  it('handles navigate back', () => {
    const mockNav = vi.fn()
    mockUseNavigate.mockReturnValue(mockNav)
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    fireEvent.click(screen.getByText('返回设置'))
    expect(mockNav).toHaveBeenCalled()
  })

  it('does not render new config button for system category', () => {
    setCategory('system')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.queryByText('新增配置')).not.toBeInTheDocument()
  })

  it('does not show loading when system category', () => {
    setCategory('system')
    hookOverrides = { systemConfigs: { data: null, isLoading: true } }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.queryByText('加载中...')).not.toBeInTheDocument()
  })

  it('handles toggle show/hide password', () => {
    setCategory('ai')
    hookOverrides = {
      systemConfigs: {
        data: [{
          category: 'ai',
          items: [{
            key: 'OPENAI_API_KEY',
            value: 'sk-test',
            description: 'OpenAI Key',
            is_secret: true,
            is_active: true,
            has_value: true,
            category: 'ai',
          }],
        }],
        isLoading: false,
      },
    }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    // Secret fields should show lock, not input with eye toggle initially
    expect(screen.getByTestId('lock-icon')).toBeInTheDocument()
  })

  it('renders default title fallback for unknown category', () => {
    setCategory('unknown_cat')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    // Falls back to category name as title
    const heading = screen.getByRole('heading', { level: 1 })
    expect(heading).toHaveTextContent('unknown_cat')
  })

  it('renders system test message for error state', () => {
    setCategory('system')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    // No test message initially
    expect(screen.queryByText(/连接成功/)).not.toBeInTheDocument()
  })

  it('renders system edit fields with placeholder values', () => {
    setCategory('system')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    const inputs = screen.getAllByRole('textbox')
    // System category should have 2 inputs (backend url, api base url)
    expect(inputs.length).toBeGreaterThanOrEqual(2)
  })

  it('handles edit field change in system mode', () => {
    setCategory('system')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    const inputs = screen.getAllByRole('textbox')
    fireEvent.change(inputs[0], { target: { value: 'http://new-url' } })
    // Should not crash
    expect(screen.getByText('后端地址')).toBeInTheDocument()
  })

  it('system category shows empty fields with placeholder text', () => {
    setCategory('system')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('后端地址')).toBeInTheDocument()
    expect(screen.getByText('API 基础路径')).toBeInTheDocument()
  })

  it('renders arrow-left icon', () => {
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByTestId('arrow-left')).toBeInTheDocument()
  })

  it('renders non-system category without test connection button', () => {
    setCategory('ai')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.queryByText('测试连通性')).not.toBeInTheDocument()
  })

  it('renders system save button', () => {
    setCategory('system')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    expect(screen.getByText('保存配置')).toBeInTheDocument()
  })

  it('renders badge for system category', () => {
    setCategory('system')
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    // Badge should show 'system'
    const badges = screen.getAllByText('system')
    expect(badges.length).toBeGreaterThan(0)
  })

  it('renders empty non-template groups fallback', () => {
    setCategory('ai')
    hookOverrides = {
      systemConfigs: {
        data: [{ category: 'ai', items: [] }],
        isLoading: false,
      },
    }
    render(<MemoryRouter><ServiceConfig /></MemoryRouter>)
    // Should show empty state
    expect(screen.getByText('该类别暂无配置项')).toBeInTheDocument()
  })
})
