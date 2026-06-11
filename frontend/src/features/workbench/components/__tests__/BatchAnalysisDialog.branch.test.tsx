/**
 * BatchAnalysisDialog - additional branch coverage tests
 * Targets uncovered branches in BatchAnalysisDialog.tsx
 */

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

describe('BatchAnalysisDialog - branch coverage', () => {
  const defaultProps = {
    modelName: 'GPT-4o',
    onSubmit: vi.fn().mockResolvedValue(undefined),
    disabled: false,
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  // Branch: readDirectoryEntries - directory entry with files (line 43-71)
  // Branch: handleDrop with file entry (line 114-125)
  it('handles drop event with file entry (webkitGetAsEntry)', async () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const dropZone = screen.getByText(/点击选择文件/).closest('div')!
    const file = new File(['test'], 'dropped.docx', { type: 'application/vnd.openxmlformats' })
    const mockEntry = {
      isFile: true,
      isDirectory: false,
      name: 'dropped.docx',
      file: (cb: Function) => cb(file),
    }
    fireEvent.drop(dropZone, {
      dataTransfer: {
        items: [{ webkitGetAsEntry: () => mockEntry }],
      },
    })
    await waitFor(() => {
      expect(screen.getByText('dropped.docx')).toBeInTheDocument()
    })
  })

  // Branch: handleDrop with no items (line 105)
  it('handles drop with empty dataTransfer items', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const dropZone = screen.getByText(/点击选择文件/).closest('div')!
    fireEvent.drop(dropZone, {
      dataTransfer: { items: [] },
    })
    expect(screen.getByText(/点击选择文件/)).toBeInTheDocument()
  })

  // Branch: handleDrop with non-supported extension file entry
  it('ignores non-supported extension files on drop', async () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const dropZone = screen.getByText(/点击选择文件/).closest('div')!
    const file = new File(['test'], 'test.txt', { type: 'text/plain' })
    const mockEntry = {
      isFile: true,
      isDirectory: false,
      name: 'test.txt',
      file: (cb: Function) => cb(file),
    }
    fireEvent.drop(dropZone, {
      dataTransfer: {
        items: [{ webkitGetAsEntry: () => mockEntry }],
      },
    })
    // .txt not supported, should not be added
    await waitFor(() => {
      expect(screen.queryByText('test.txt')).not.toBeInTheDocument()
    })
  })

  // Branch: handleDrop with directory entry (line 126-131)
  it('handles drop with directory entry', async () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const dropZone = screen.getByText(/点击选择文件/).closest('div')!
    const file = new File(['test'], 'nested.docx', { type: 'application/vnd.openxmlformats' })
    let callCount = 0
    const mockDirEntry = {
      isFile: false,
      isDirectory: true,
      name: 'mydir',
      createReader: () => ({
        readEntries: (cb: Function) => {
          callCount++
          if (callCount === 1) {
            cb([{
              isFile: true,
              isDirectory: false,
              name: 'nested.docx',
              file: (cb2: Function) => cb2(file),
            }])
          } else {
            cb([]) // empty = done
          }
        },
      }),
    }
    fireEvent.drop(dropZone, {
      dataTransfer: {
        items: [{ webkitGetAsEntry: () => mockDirEntry }],
      },
    })
    await waitFor(() => {
      expect(screen.getByText('nested.docx')).toBeInTheDocument()
    })
  })

  // Branch: handleDrop with null webkitGetAsEntry (line 113)
  it('handles drop with null webkitGetAsEntry', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const dropZone = screen.getByText(/点击选择文件/).closest('div')!
    fireEvent.drop(dropZone, {
      dataTransfer: {
        items: [{ webkitGetAsEntry: () => null }],
      },
    })
    // Should not crash
    expect(screen.getByText(/点击选择文件/)).toBeInTheDocument()
  })

  // Branch: handleFileChange with file input reset (line 96)
  it('resets file input after change', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.docx', { type: '' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    // File input value should be reset
    expect(fileInput.value).toBe('')
  })

  // Branch: handleOptimizePrompt with non-Error exception (line 163)
  it('AI optimize handles non-Error exception', async () => {
    const alertSpy = vi.spyOn(window, 'alert').mockImplementation(() => {})
    mockOptimizePrompt.mockRejectedValue('string error')
    render(<BatchAnalysisDialog {...defaultProps} />)
    fireEvent.click(screen.getByText('竞业限制'))
    fireEvent.click(screen.getByText('AI 优化'))
    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith(expect.stringContaining('未知错误'))
    })
    alertSpy.mockRestore()
  })

  // Branch: handleOptimizePrompt when prompt is empty (line 156)
  it('AI optimize does nothing when prompt is empty', async () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const optimizeBtn = screen.getByText('AI 优化')
    expect(optimizeBtn).toBeDisabled()
    // Clicking disabled button should not call API
    fireEvent.click(optimizeBtn)
    expect(mockOptimizePrompt).not.toHaveBeenCalled()
  })

  // Branch: handleOptimizePrompt when already optimizing (line 156)
  it('AI optimize button disabled during optimization', async () => {
    mockOptimizePrompt.mockImplementation(() => new Promise(() => {})) // never resolves
    render(<BatchAnalysisDialog {...defaultProps} />)
    fireEvent.click(screen.getByText('竞业限制'))
    fireEvent.click(screen.getByText('AI 优化'))
    await waitFor(() => {
      expect(screen.getByText('优化中...')).toBeInTheDocument()
    })
  })

  // Branch: handleSubmit with empty files (line 170)
  it('submit does nothing when no files', () => {
    const onSubmit = vi.fn()
    render(<BatchAnalysisDialog {...defaultProps} onSubmit={onSubmit} />)
    fireEvent.click(screen.getByText('竞业限制'))
    // Submit button is disabled with 0 files
    expect(screen.getByText('开始分析 (0 个文件)')).toBeDisabled()
  })

  // Branch: handleSubmit with empty prompt (line 170)
  it('submit does nothing when prompt is empty', () => {
    const onSubmit = vi.fn()
    render(<BatchAnalysisDialog {...defaultProps} onSubmit={onSubmit} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.docx', { type: '' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    // Submit button disabled since no prompt
    expect(screen.getByText('开始分析 (1 个文件)')).toBeDisabled()
  })

  // Branch: handleSubmit success resets all fields (line 174-178)
  it('submit resets concurrency and post-analysis prompt', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<BatchAnalysisDialog {...defaultProps} onSubmit={onSubmit} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.docx', { type: '' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    fireEvent.click(screen.getByText('竞业限制'))
    fireEvent.change(screen.getByPlaceholderText(/留空则直接下载/), { target: { value: 'post prompt' } })
    fireEvent.click(screen.getByText(/开始分析/))
    await waitFor(() => {
      expect(screen.getByText('开始分析 (0 个文件)')).toBeInTheDocument()
    })
    // Post-analysis prompt should be cleared
    expect(screen.getByPlaceholderText(/留空则直接下载/)).toHaveValue('')
  })

  // Branch: concurrency input with out of range value (line 337)
  it('ignores concurrency values outside 1-100 range', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const inputs = screen.getAllByRole('spinbutton')
    const numberInput = inputs[0]
    fireEvent.change(numberInput, { target: { value: '0' } })
    expect(numberInput).toHaveValue(50) // default unchanged
    fireEvent.change(numberInput, { target: { value: '101' } })
    expect(numberInput).toHaveValue(50) // default unchanged
  })

  // Branch: range slider changes concurrency (line 327)
  it('range slider changes concurrency value', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const rangeInput = document.querySelector('input[type="range"]') as HTMLInputElement
    fireEvent.change(rangeInput, { target: { value: '75' } })
    // The number input should reflect this
    const inputs = screen.getAllByRole('spinbutton')
    expect(inputs[0]).toHaveValue(75)
  })

  // Branch: modelName with empty string shows "默认模型" (line 365)
  it('shows "默认模型" when modelName is empty', () => {
    render(<BatchAnalysisDialog {...defaultProps} modelName="" />)
    expect(screen.getByText('默认模型')).toBeInTheDocument()
  })

  // Branch: drag over sets dragging state (line 142)
  it('shows upload icon when dragging', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const dropZone = screen.getByText(/点击选择文件/).closest('div')!
    fireEvent.dragOver(dropZone)
    expect(screen.getByTestId('upload')).toBeInTheDocument()
  })

  // Branch: drag leave resets dragging state (line 148)
  it('hides upload icon after drag leave', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const dropZone = screen.getByText(/点击选择文件/).closest('div')!
    fireEvent.dragOver(dropZone)
    expect(screen.getByTestId('upload')).toBeInTheDocument()
    fireEvent.dragLeave(dropZone)
    expect(screen.queryByTestId('upload')).not.toBeInTheDocument()
  })

  // Branch: submit resets form including files and prompt
  it('submit resets files and prompt after success', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    render(<BatchAnalysisDialog {...defaultProps} onSubmit={onSubmit} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file = new File(['test'], 'test.docx', { type: '' })
    fireEvent.change(fileInput, { target: { files: [file] } })
    fireEvent.click(screen.getByText('竞业限制'))
    fireEvent.click(screen.getByText(/开始分析/))
    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalled()
    })
    // Form should be reset
    expect(screen.getByText('开始分析 (0 个文件)')).toBeInTheDocument()
    expect(screen.getByTestId('batch-prompt')).toHaveValue('')
  })

  // Branch: file input with multiple files including duplicates (line 84-89)
  it('deduplicates files by name', () => {
    render(<BatchAnalysisDialog {...defaultProps} />)
    const fileInput = document.querySelector('input[type="file"]') as HTMLInputElement
    const file1 = new File(['a'], 'same.docx', { type: '' })
    const file2 = new File(['b'], 'same.docx', { type: '' })
    const file3 = new File(['c'], 'other.docx', { type: '' })
    fireEvent.change(fileInput, { target: { files: [file1] } })
    fireEvent.change(fileInput, { target: { files: [file2, file3] } })
    // same.docx should not be duplicated, but other.docx should be added
    const allFileTexts = screen.getAllByText('same.docx')
    expect(allFileTexts).toHaveLength(1)
    expect(screen.getByText('other.docx')).toBeInTheDocument()
  })
})
