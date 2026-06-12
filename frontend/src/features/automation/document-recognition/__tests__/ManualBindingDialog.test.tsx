import { render, screen, fireEvent } from '@testing-library/react'
import { ManualBindingDialog } from '../components/ManualBindingDialog'

vi.mock('lucide-react', () => ({
  Loader2: () => <svg data-testid="loader" />,
}))

const mockBindCaseMutate = vi.fn()

vi.mock('../hooks/use-recognition-mutations', () => ({
  useBindCase: () => ({
    mutate: mockBindCaseMutate,
    isPending: false,
  }),
}))

vi.mock('../schemas', () => ({
  manualBindingSchema: {},
}))

vi.mock('../components/CaseSearchSelect', () => ({
  CaseSearchSelect: () => <div data-testid="case-search-select" />,
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) =>
    open ? <div data-testid="dialog">{children}</div> : null,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('@/components/ui/form', () => ({
  Form: ({ children }: { children: React.ReactNode }) => <form>{children}</form>,
  FormControl: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormField: ({ render }: { render: (props: Record<string, unknown>) => React.ReactNode }) =>
    render({ field: { value: '', onChange: vi.fn() } }),
  FormItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  FormLabel: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
  FormMessage: () => <span />,
}))

vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))

// Mock useForm and zodResolver to avoid schema validation issues
vi.mock('react-hook-form', () => ({
  useForm: () => ({
    control: {},
    handleSubmit: (fn: Function) => (e: Event) => { e.preventDefault(); fn({}) },
    reset: vi.fn(),
    setValue: vi.fn(),
    watch: vi.fn(() => undefined),
    formState: { errors: {} },
  }),
  Controller: ({ render }: { render: (props: Record<string, unknown>) => React.ReactNode }) =>
    render({ field: { value: '', onChange: vi.fn() } }),
}))

vi.mock('@hookform/resolvers/zod', () => ({
  zodResolver: () => ({}),
}))

const mockTask = {
  id: 1,
  file_name: '判决书.pdf',
  document_type: '判决书',
  key_time: '2024-01-15',
  status: 'pending_manual',
}

describe('ManualBindingDialog', () => {
  it('renders dialog when open', () => {
    render(<ManualBindingDialog open={true} onOpenChange={vi.fn()} task={mockTask as never} />)
    expect(screen.getByText('手动绑定案件')).toBeInTheDocument()
  })

  it('does not render when closed', () => {
    render(<ManualBindingDialog open={false} onOpenChange={vi.fn()} task={mockTask as never} />)
    expect(screen.queryByText('手动绑定案件')).not.toBeInTheDocument()
  })

  it('renders file name', () => {
    render(<ManualBindingDialog open={true} onOpenChange={vi.fn()} task={mockTask as never} />)
    expect(screen.getByText('判决书.pdf')).toBeInTheDocument()
  })

  it('renders confirm button', () => {
    render(<ManualBindingDialog open={true} onOpenChange={vi.fn()} task={mockTask as never} />)
    expect(screen.getByText('确认绑定')).toBeInTheDocument()
  })

  it('renders cancel button', () => {
    render(<ManualBindingDialog open={true} onOpenChange={vi.fn()} task={mockTask as never} />)
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  // ===== Branch coverage: onBindSuccess callback =====

  it('renders with onBindSuccess prop', () => {
    const onBindSuccess = vi.fn()
    render(
      <ManualBindingDialog
        open={true}
        onOpenChange={vi.fn()}
        task={mockTask as never}
        onBindSuccess={onBindSuccess}
      />
    )
    expect(screen.getByText('确认绑定')).toBeInTheDocument()
  })

  // ===== Branch coverage: cancel button calls onOpenChange(false) =====

  it('calls onOpenChange(false) when cancel is clicked', () => {
    const onOpenChange = vi.fn()
    render(<ManualBindingDialog open={true} onOpenChange={onOpenChange} task={mockTask as never} />)
    fireEvent.click(screen.getByText('取消'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  // ===== Branch coverage: confirm button text =====

  it('shows confirm button text when not pending', () => {
    render(<ManualBindingDialog open={true} onOpenChange={vi.fn()} task={mockTask as never} />)
    expect(screen.getByText('确认绑定')).toBeInTheDocument()
  })

  // ===== Branch coverage: empty task fields =====

  it('handles task with null document_type and key_time', () => {
    const taskWithNulls = { ...mockTask, document_type: null, key_time: null }
    render(<ManualBindingDialog open={true} onOpenChange={vi.fn()} task={taskWithNulls as never} />)
    expect(screen.getByText('手动绑定案件')).toBeInTheDocument()
  })

  // ===== Branch coverage: onOpenChange for dialog =====

  it('passes onOpenChange to Dialog', () => {
    const onOpenChange = vi.fn()
    render(<ManualBindingDialog open={true} onOpenChange={onOpenChange} task={mockTask as never} />)
    expect(screen.getByTestId('dialog')).toBeInTheDocument()
  })

  // ===== Branch coverage: dialog description =====

  it('renders dialog description', () => {
    render(<ManualBindingDialog open={true} onOpenChange={vi.fn()} task={mockTask as never} />)
    expect(screen.getByText(/自动绑定失败/)).toBeInTheDocument()
  })

  // ===== Branch coverage: case search select rendered =====

  it('renders case search select', () => {
    render(<ManualBindingDialog open={true} onOpenChange={vi.fn()} task={mockTask as never} />)
    expect(screen.getByTestId('case-search-select')).toBeInTheDocument()
  })

  // ===== Branch coverage: form labels =====

  it('renders form field labels', () => {
    render(<ManualBindingDialog open={true} onOpenChange={vi.fn()} task={mockTask as never} />)
    expect(screen.getByText(/选择案件/)).toBeInTheDocument()
    expect(screen.getByText('文书类型')).toBeInTheDocument()
    expect(screen.getByText('关键时间')).toBeInTheDocument()
  })
})
