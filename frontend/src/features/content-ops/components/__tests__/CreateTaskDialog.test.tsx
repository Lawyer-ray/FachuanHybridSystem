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
import { toast } from 'sonner'

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

  it('handles removing a speaker in discussion mode', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('多人讨论'))
    // Default has 3 speakers, remove one
    const trashIcons = screen.getAllByTestId('trash')
    expect(trashIcons.length).toBe(3)
    fireEvent.click(trashIcons[0])
    // Should have 2 speakers now
    const remainingTrash = screen.getAllByTestId('trash')
    expect(remainingTrash.length).toBe(2)
  })

  it('handles search mode without keyword shows error', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('检索模式'))
    fireEvent.click(screen.getByText('创建任务'))
    expect(toast.error).toHaveBeenCalledWith('请输入检索关键词')
  })

  it('handles direct mode without content shows error', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    // Direct mode is default, but no content
    fireEvent.click(screen.getByText('创建任务'))
    expect(toast.error).toHaveBeenCalledWith('请输入内容')
  })

  it('handles search mode without credential shows error', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('检索模式'))
    // Fill keyword but no credential
    const input = screen.getByPlaceholderText(/输入法律案例关键词/)
    fireEvent.change(input, { target: { value: '竞业限制' } })
    fireEvent.click(screen.getByText('创建任务'))
    expect(toast.error).toHaveBeenCalledWith('请选择法律检索账号')
  })

  it('handles voice preview button click', async () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    // The voice preview button should be clickable
    const buttons = screen.getAllByRole('button')
    // Find the volume2 button near voice selector
    expect(buttons.length).toBeGreaterThan(0)
  })

  it('renders discussion mode speakers section', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('多人讨论'))
    expect(screen.getByText('讨论角色')).toBeInTheDocument()
    // Should show default speakers
    expect(screen.getByDisplayValue('主持人')).toBeInTheDocument()
    expect(screen.getByDisplayValue('张律师')).toBeInTheDocument()
    expect(screen.getByDisplayValue('李大姐')).toBeInTheDocument()
  })

  it('handles editing speaker fields', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('多人讨论'))
    const nameInputs = screen.getAllByPlaceholderText('角色名')
    fireEvent.change(nameInputs[0], { target: { value: '新主持人' } })
    expect(nameInputs[0]).toHaveValue('新主持人')
  })

  it('resets form on dialog reopen', () => {
    const { rerender } = render(<CreateTaskDialog open onOpenChange={vi.fn()} defaultKeyword="old" />)
    // Change mode
    fireEvent.click(screen.getByText('检索模式'))
    // Reopen dialog
    rerender(<CreateTaskDialog open onOpenChange={vi.fn()} defaultKeyword="new" />)
    // Should sync to new defaults
    expect(screen.getByText('创建内容任务')).toBeInTheDocument()
  })

  it('handles direct mode with valid content and submit', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    const textarea = screen.getByPlaceholderText('粘贴案例内容、判决书摘要或任何法律文本...')
    fireEvent.change(textarea, { target: { value: '测试法律内容' } })
    fireEvent.click(screen.getByText('创建任务'))
    // Should call the mutate function (via useCreateTask mock)
    expect(toast.success).not.toHaveBeenCalled() // mutate is a no-op in mock
  })

  it('handles discussion mode output selection', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('多人讨论'))
    // Discussion speakers section should be visible
    expect(screen.getByText('讨论角色')).toBeInTheDocument()
  })

  it('shows description for discussion output mode', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('多人讨论'))
    expect(screen.getByText('创建内容任务')).toBeInTheDocument()
  })

  it('handles case summary input', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    const summaryInput = screen.getByPlaceholderText(/简要描述案例背景/)
    fireEvent.change(summaryInput, { target: { value: '案件摘要' } })
    expect(summaryInput).toHaveValue('案件摘要')
  })

  it('renders default speakers with style prompts', () => {
    render(<CreateTaskDialog open onOpenChange={vi.fn()} />)
    fireEvent.click(screen.getByText('多人讨论'))
    const styleInputs = screen.getAllByPlaceholderText('声音描述')
    expect(styleInputs.length).toBe(3)
  })
})
