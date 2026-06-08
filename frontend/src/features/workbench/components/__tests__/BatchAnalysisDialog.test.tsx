vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children, className }: { children: React.ReactNode; className?: string }) => <div className={className}>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, title, className, ...props }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} title={title as string} className={className as string} {...props}>
      {children}
    </button>
  ),
}))

vi.mock('@/components/ui/input', () => ({
  Input: ({ value, onChange, className, ...props }: Record<string, unknown>) => (
    <input value={value as string} onChange={onChange as React.ChangeEventHandler} className={className as string} {...props} />
  ),
}))

vi.mock('@/components/ui/label', () => ({
  Label: ({ children, htmlFor }: { children: React.ReactNode; htmlFor?: string }) => <label htmlFor={htmlFor}>{children}</label>,
}))

vi.mock('@/components/ui/textarea', () => ({
  Textarea: ({ value, onChange, placeholder, id, rows, className }: Record<string, unknown>) => (
    <textarea data-testid={id} value={value as string} onChange={onChange as React.ChangeEventHandler} placeholder={placeholder as string} rows={rows as number} className={className as string} />
  ),
}))

vi.mock('@/components/ui/badge', () => ({
  Badge: ({ children, variant, className }: Record<string, unknown>) => <span className={className as string} data-variant={variant}>{children}</span>,
}))

const mockOptimizePrompt = vi.fn()

vi.mock('../../api', () => ({
  optimizePrompt: (...args: unknown[]) => mockOptimizePrompt(...args),
}))

vi.mock('lucide-react', () => ({
  FolderOpen: () => <svg data-testid="folder-open" />,
  X: () => <svg data-testid="x-icon" />,
  FileText: () => <svg data-testid="file-text" />,
  Upload: () => <svg data-testid="upload" />,
  WandSparkles: () => <svg data-testid="wand" />,
  Loader2: () => <svg data-testid="loader" />,
}))

import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { BatchAnalysisDialog } from '../BatchAnalysisDialog'

describe('BatchAnalysisDialog', () => {
  const defaultProps = {
    modelName: 'GPT-4o',
    onSubmit: vi.fn().mockResolvedValue(undefined),
    disabled: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders dialog title', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText('批量文档分析')).toBeInTheDocument()
  })

  it('renders description text', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText(/上传 Word 文件/)).toBeInTheDocument()
  })

  it('renders preset prompt buttons', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText('竞业限制')).toBeInTheDocument()
    expect(screen.getByText('劳动争议')).toBeInTheDocument()
    expect(screen.getByText('合同纠纷')).toBeInTheDocument()
    expect(screen.getByText('侵权责任')).toBeInTheDocument()
  })

  it('displays model name badge', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText('GPT-4o')).toBeInTheDocument()
  })

  it('shows default model text when no model name', () => {
    render(<BatchAnalysisDialog {...defaultProps} modelName="" />)
    expect(screen.getByText('默认模型')).toBeInTheDocument()
  })

  it('renders concurrency slider', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByLabelText('并发数')).toBeInTheDocument()
  })

  it('shows submit button with file count', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText('开始分析 (0 个文件)')).toBeInTheDocument()
  })

  it('renders file drop zone', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText(/点击选择文件/)).toBeInTheDocument()
  })

  it('renders analysis prompt textarea', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText('分析要求')).toBeInTheDocument()
  })

  it('renders AI optimize button', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText('AI 优化')).toBeInTheDocument()
  })

  it('renders post-analysis prompt section', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText(/后处理提示词/)).toBeInTheDocument()
  })

  it('renders cancel button', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  it('renders concurrency description', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText(/同时调用 AI 分析的并发数量/)).toBeInTheDocument()
  })

  it('renders post-analysis description', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText(/填写后，所有分析结果将发送给主 AI/)).toBeInTheDocument()
  })

  it('clicking preset sets prompt text', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    fireEvent.click(screen.getByText('竞业限制'))
    const textarea = screen.getByTestId('batch-prompt')
    expect(textarea).toHaveValue('分析每一个案例的争议焦点和裁判要旨，弄清楚每个案例中关于竞业限制的裁判标准，总结竞业限制条款如何适用。')
  })

  it('clicking labor dispute preset sets prompt', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    fireEvent.click(screen.getByText('劳动争议'))
    const textarea = screen.getByTestId('batch-prompt')
    expect((textarea as HTMLTextAreaElement).value).toContain('劳动争议')
  })

  it('clicking contract preset sets prompt', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    fireEvent.click(screen.getByText('合同纠纷'))
    const textarea = screen.getByTestId('batch-prompt')
    expect((textarea as HTMLTextAreaElement).value).toContain('合同效力')
  })

  it('clicking tort preset sets prompt', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    fireEvent.click(screen.getByText('侵权责任'))
    const textarea = screen.getByTestId('batch-prompt')
    expect((textarea as HTMLTextAreaElement).value).toContain('侵权行为')
  })

  it('changes concurrency value', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const inputs = screen.getAllByRole('spinbutton')
    const numberInput = inputs[0]
    fireEvent.change(numberInput, { target: { value: '30' } })
    expect(numberInput).toHaveValue(30)
  })

  it('changes concurrency number input', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const inputs = screen.getAllByRole('spinbutton')
    const numberInput = inputs[0]
    fireEvent.change(numberInput, { target: { value: '25' } })
    expect(numberInput).toHaveValue(25)
  })

  it('ignores out of range concurrency values', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const inputs = screen.getAllByRole('spinbutton')
    const numberInput = inputs[0]
    fireEvent.change(numberInput, { target: { value: '0' } })
    // Value should not change to 0 (min is 1)
    expect(numberInput).toHaveValue(50) // default
  })

  it('ignores concurrency > 100', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const inputs = screen.getAllByRole('spinbutton')
    const numberInput = inputs[0]
    fireEvent.change(numberInput, { target: { value: '150' } })
    expect(numberInput).toHaveValue(50) // default
  })

  it('accepts concurrency at min boundary', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const inputs = screen.getAllByRole('spinbutton')
    const numberInput = inputs[0]
    fireEvent.change(numberInput, { target: { value: '1' } })
    expect(numberInput).toHaveValue(1)
  })

  it('accepts concurrency at max boundary', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const inputs = screen.getAllByRole('spinbutton')
    const numberInput = inputs[0]
    fireEvent.change(numberInput, { target: { value: '100' } })
    expect(numberInput).toHaveValue(100)
  })

  it('post-analysis prompt changes', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const textarea = screen.getByPlaceholderText(/留空则直接下载/)
    fireEvent.change(textarea, { target: { value: '对比分析' } })
    expect(textarea).toHaveValue('对比分析')
  })

  it('submit button disabled when no files', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const submitBtn = screen.getByText('开始分析 (0 个文件)')
    expect(submitBtn).toBeDisabled()
  })

  it('submit button disabled when no prompt', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    // Without files and without prompt, submit should be disabled
    const submitBtn = screen.getByText('开始分析 (0 个文件)')
    expect(submitBtn).toBeDisabled()
  })

  it('AI optimize button disabled when no prompt', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const optimizeBtn = screen.getByText('AI 优化')
    expect(optimizeBtn).toBeDisabled()
  })

  it('renders file input element', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]')
    expect(fileInput).toBeInTheDocument()
    expect(fileInput).toHaveAttribute('accept', '.doc,.docx,.xls,.xlsx')
  })

  it('renders description for supported formats', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText(/支持 .doc、.docx、.xls、.xlsx 格式/)).toBeInTheDocument()
  })

  it('renders description about folder drag', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    expect(screen.getByText(/拖入文件夹会自动提取/)).toBeInTheDocument()
  })

  it('renders disabled state', () => {
    render(<BatchAnalysisDialog {...defaultProps} disabled />)
    // The trigger button should be disabled
    const buttons = screen.getAllByRole('button')
    const triggerBtn = buttons.find(b => b.hasAttribute('disabled'))
    // At least the submit button should be disabled
    expect(screen.getByText('开始分析 (0 个文件)')).toBeDisabled()
  })

  it('handles drag over event', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const dropZone = screen.getByText(/点击选择文件/).closest('div')!
    fireEvent.dragOver(dropZone)
    // Should not crash
    expect(dropZone).toBeInTheDocument()
  })

  it('handles drag leave event', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const dropZone = screen.getByText(/点击选择文件/).closest('div')!
    fireEvent.dragOver(dropZone)
    fireEvent.dragLeave(dropZone)
    expect(dropZone).toBeInTheDocument()
  })

  it('AI optimize calls API', async () => {
    mockOptimizePrompt.mockResolvedValue({ optimized_prompt: '优化后的提示词' })
    render(<BatchAnalysisDialog {...defaultProps} />)
    // Set prompt first
    fireEvent.click(screen.getByText('竞业限制'))
    // Click optimize
    fireEvent.click(screen.getByText('AI 优化'))
    await waitFor(() => {
      expect(mockOptimizePrompt).toHaveBeenCalled()
    })
  })

  it('AI optimize handles error', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
    mockOptimizePrompt.mockRejectedValue(new Error('API error'))
    render(<BatchAnalysisDialog {...defaultProps} />)
    fireEvent.click(screen.getByText('竞业限制'))
    fireEvent.click(screen.getByText('AI 优化'))
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalled()
    })
    alertSpy.mockRestore()
  })

  it('cancel button works', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    fireEvent.click(screen.getByText('取消'))
    // Should not crash
    expect(screen.getByText('批量文档分析')).toBeInTheDocument()
  })

  it('renders concurrency range slider', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const rangeInput = document.querySelector('input[type="range"]')
    expect(rangeInput).toBeInTheDocument()
    expect(rangeInput).toHaveAttribute('min', '1')
    expect(rangeInput).toHaveAttribute('max', '100')
  })

  it('handles file input change with no files', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(fileInput, { target: { files: null } })
    // Should not crash
    expect(screen.getByText('开始分析 (0 个文件)')).toBeInTheDocument()
  })

  it('renders optimize button disabled when optimizing', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    // Initially disabled since no prompt
    expect(screen.getByText('AI 优化')).toBeDisabled()
  })

  it('handles file input change with valid files', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(screen.getByText('test.docx')).toBeInTheDocument()
  })

  it('shows file list after adding files', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file1 = new File(['test1'], 'doc1.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const file2 = new File(['test2'], 'doc2.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    fireEvent.change(fileInput, { target: { files: [file1, file2] } })
    expect(screen.getByText('doc1.docx')).toBeInTheDocument()
    expect(screen.getByText('doc2.xlsx')).toBeInTheDocument()
  })

  it('removes file from list', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(screen.getByText('test.docx')).toBeInTheDocument()
    // Remove file
    const removeBtns = screen.getAllByTestId('x-icon')
    fireEvent.click(removeBtns[0])
    expect(screen.queryByText('test.docx')).not.toBeInTheDocument()
  })

  it('shows file badges with extension', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(screen.getByText('DOCX')).toBeInTheDocument()
  })

  it('shows continue add button when files are selected', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    expect(screen.getByText('继续添加')).toBeInTheDocument()
  })

  it('update button count with file selection', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    // Click a preset to set prompt
    fireEvent.click(screen.getByText('竞业限制'))
    expect(screen.getByText('开始分析 (1 个文件)')).toBeInTheDocument()
  })

  it('submit calls onSubmit with correct args', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<BatchAnalysisDialog {...defaultProps} onSubmit={onSubmit} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    fireEvent.click(screen.getByText('竞业限制'))
    fireEvent.click(screen.getByText(/开始分析/))
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledWith(
        expect.stringContaining('竞业限制'),
        [file],
        '',
        50,
      )
    })
  })

  it('submit resets form on success', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<BatchAnalysisDialog {...defaultProps} onSubmit={onSubmit} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    fireEvent.click(screen.getByText('竞业限制'))
    fireEvent.click(screen.getByText(/开始分析/))
    await waitFor(() => {
      expect(screen.getByText('开始分析 (0 个文件)')).toBeInTheDocument()
    })
  })

  it('handles drop event with files', async () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const dropZone = screen.getByText(/点击选择文件/).closest('div')!
    const file = new File(['test'], 'dropped.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.drop(dropZone, { dataTransfer: { items: [{ webkitGetAsEntry: () => ({ isFile: true, isDirectory: false, name: 'dropped.docx', file: (cb: Function) => cb(file) }) }] } })
    await waitFor(() => {
      expect(screen.getByText('dropped.docx')).toBeInTheDocument()
    })
  })

  it('concurrency input validates within range', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const inputs = screen.getAllByRole('spinbutton')
    const numberInput = inputs[0]
    fireEvent.change(numberInput, { target: { value: '75' } })
    expect(numberInput).toHaveValue(75)
  })

  it('post-analysis prompt textarea works', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const textarea = screen.getByPlaceholderText(/留空则直接下载/)
    fireEvent.change(textarea, { target: { value: '对比分析所有案例' } })
    expect(textarea).toHaveValue('对比分析所有案例')
  })

  it('no duplicate files when same file added twice', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.docx', { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    fireEvent.change(fileInput, { target: { files: [file] } })
    // Should only have 1 file
    expect(screen.getByText('开始分析 (1 个文件)')).toBeInTheDocument()
  })
})
