/**
 * ElementConvertTool Component Tests
 * 测试要素式转换工具组件
 */

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/api', () => ({
  api: { get: vi.fn(), post: vi.fn() },
}))

vi.mock('@tanstack/react-query', () => ({
  useQuery: vi.fn(),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, className }: Record<string, unknown>) => <div className={className as string}>{children}</div>,
  CardContent: ({ children, className }: Record<string, unknown>) => <div className={className as string}>{children}</div>,
}))

vi.mock('ky', () => ({
  HTTPError: class HTTPError extends Error {},
}))

import { render, screen } from '@testing-library/react'
import { ElementConvertTool } from '../ElementConvertTool'
import { useQuery } from '@tanstack/react-query'

describe('ElementConvertTool', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders page title', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText('要素式转换')).toBeInTheDocument()
  })

  it('renders step indicators', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText('上传文书')).toBeInTheDocument()
    expect(screen.getByText('选择格式')).toBeInTheDocument()
    expect(screen.getByText('转换下载')).toBeInTheDocument()
  })

  it('renders upload area when no file selected', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText(/点击选择或拖拽文件到此处/)).toBeInTheDocument()
    expect(screen.getByText(/支持 .docx、.doc、.pdf 格式/)).toBeInTheDocument()
  })

  it('shows loading state for format list', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: true } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText('加载格式列表...')).toBeInTheDocument()
  })

  it('renders category list when data is loaded', () => {
    vi.mocked(useQuery).mockReturnValue({
      data: {
        categories: [
          { category: '合同纠纷', items: [{ mbid: 'mb1', name: '买卖合同' }, { mbid: 'mb2', name: '借款合同' }] },
        ],
      },
      isLoading: false,
    } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText('合同纠纷')).toBeInTheDocument()
    expect(screen.getByText('买卖合同')).toBeInTheDocument()
    expect(screen.getByText('借款合同')).toBeInTheDocument()
  })

  it('renders description text', () => {
    vi.mocked(useQuery).mockReturnValue({ data: null, isLoading: false } as any)
    render(<ElementConvertTool />)
    expect(screen.getByText(/上传传统格式文书，系统自动识别并转换为要素式标准格式/)).toBeInTheDocument()
  })
})
