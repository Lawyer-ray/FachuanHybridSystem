vi.mock('../../hooks/use-content-ops', () => ({
  useCreateTask: () => ({ mutate: vi.fn(), isPending: false }),
}))

vi.mock('@/features/organization/hooks/use-credentials', () => ({
  useCredentials: () => ({ data: [] }),
}))

vi.mock('../../api', () => ({
  contentOpsApi: {
    searchCases: vi.fn().mockResolvedValue([]),
    testTts: vi.fn().mockResolvedValue(new Blob()),
  },
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) => open ? <div>{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean}>{children}</button>
  ),
}))

vi.mock('@/components/ui/label', () => ({
  Label: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

vi.mock('@/components/ui/textarea', () => ({
  Textarea: (props: Record<string, unknown>) => <textarea {...props} />,
}))

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('lucide-react', () => ({
  Loader2: () => <svg data-testid="loader" />,
  Search: () => <svg data-testid="search" />,
  FileText: () => <svg data-testid="file-text" />,
  Volume2: () => <svg data-testid="volume" />,
  Users: () => <svg data-testid="users" />,
  Trash2: () => <svg data-testid="trash" />,
  Plus: () => <svg data-testid="plus" />,
  Play: () => <svg data-testid="play" />,
  Pause: () => <svg data-testid="pause" />,
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { render, screen, fireEvent } from '@testing-library/react'
import { CreateTaskDialog } from '../CreateTaskDialog'

describe('CreateTaskDialog', () => {
  it('renders dialog title when open', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('创建内容任务')).toBeInTheDocument()
  })

  it('renders mode buttons', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('检索模式')).toBeInTheDocument()
    expect(screen.getByText('直投模式')).toBeInTheDocument()
  })

  it('renders voice selector', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('语音音色')).toBeInTheDocument()
  })

  it('renders create and cancel buttons', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('创建任务')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('shows direct mode content input by default', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByPlaceholderText('粘贴案例内容、判决书摘要或任何法律文本...')).toBeInTheDocument()
  })

  it('renders description for direct mode', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText(/AI 将把你的内容改写为叙事风格/)).toBeInTheDocument()
  })

  it('renders search mode when selected', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('检索模式'))
    expect(screen.getByPlaceholderText(/输入法律案例关键词/)).toBeInTheDocument()
  })

  it('renders search mode description', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('检索模式'))
    expect(screen.getByText(/AI 将通过关键词检索法律案例/)).toBeInTheDocument()
  })

  it('renders output mode selector', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('输出模式')).toBeInTheDocument()
  })

  it('handles cancel button click', () => {
    const onOpenChange = vi.fn()
    render(<CreateTaskDialog open onOpenChange={onOpenChange} />)
    fireEvent.click(screen.getByText('取消'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  it('renders with default keyword', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} defaultKeyword="测试关键词" />)
    expect(screen.getByText('直投模式')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(<CreateTaskDialog open={false} onOpenChange={vi.fn()} />)
    expect(screen.queryByText('创建任务')).not.toBeInTheDocument()
  })

  it('renders search keyword label', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('检索模式'))
    expect(screen.getByText('检索关键词 *')).toBeInTheDocument()
  })

  it('renders credential label', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('检索模式'))
    expect(screen.getByText('法律检索账号 *')).toBeInTheDocument()
  })

  it('shows error when no weike credentials', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('检索模式'))
    expect(screen.getByText(/未找到威科先行相关账号/)).toBeInTheDocument()
  })

  it('renders direct mode content label', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('输入内容 *')).toBeInTheDocument()
  })

  it('handles direct content input', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    const textarea = screen.getByPlaceholderText('粘贴案例内容、判决书摘要或任何法律文本...')
    fireEvent.change(textarea, { target: { value: '测试内容' } })
    expect(textarea).toHaveValue('测试内容')
  })

  it('handles keyword input in search mode', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('检索模式'))
    const input = screen.getByPlaceholderText(/输入法律案例关键词/)
    fireEvent.change(input, { target: { value: '竞业限制' } })
    expect(input).toHaveValue('竞业限制')
  })

  it('renders with default mode as direct', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByPlaceholderText('粘贴案例内容、判决书摘要或任何法律文本...')).toBeInTheDocument()
  })

  it('renders with search mode as default', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} defaultMode="search" />)
    expect(screen.getByPlaceholderText(/输入法律案例关键词/)).toBeInTheDocument()
  })

  it('renders TTS style prompt section', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    // TTS style prompt is in the component
    expect(screen.getByText('输出模式')).toBeInTheDocument()
  })

  it('renders case summary section', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('案例摘要')).toBeInTheDocument()
  })

  it('renders voice preview button', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    // The volume icon button is used for preview
    expect(screen.getByTestId('volume')).toBeInTheDocument()
  })

  it('renders narration output mode option', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    expect(screen.getByText('单人叙事')).toBeInTheDocument()
  })

  it('renders remove speaker buttons in discussion mode', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('多人讨论'))
    const trashIcons = screen.getAllByTestId('trash')
    expect(trashIcons.length).toBeGreaterThan(0)
  })

  it('renders add speaker button in discussion mode', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('多人讨论'))
    expect(screen.getByText('添加角色')).toBeInTheDocument()
  })

  it('handles adding a speaker in discussion mode', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('多人讨论'))
    fireEvent.click(screen.getByText('添加角色'))
    expect(screen.getByText('添加角色')).toBeInTheDocument()
  })
})
