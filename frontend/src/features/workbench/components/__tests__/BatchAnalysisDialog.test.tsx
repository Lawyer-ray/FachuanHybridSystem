/**
 * BatchAnalysisDialog Component Tests
 * 测试批量文档分析对话框
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

vi.mock('../../api', () => ({
  optimizePrompt: vi.fn(),
}))

import { render, screen } from '@testing-library/react'
import { BatchAnalysisDialog } from '../BatchAnalysisDialog'

describe('BatchAnalysisDialog', () => {
  const defaultProps = {
    modelName: 'GPT-4o',
    onSubmit: vi.fn().mockResolvedValue(undefined),
    disabled: false,
  }

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
})
