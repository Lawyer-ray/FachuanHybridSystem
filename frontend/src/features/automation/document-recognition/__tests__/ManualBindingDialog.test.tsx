import { render, screen } from '@testing-library/react'
import { ManualBindingDialog } from '../components/ManualBindingDialog'

vi.mock('lucide-react', () => ({
  Loader2: () => <svg data-testid="loader" />,
}))

vi.mock('../hooks/use-recognition-mutations', () => ({
  useBindCase: () => ({
    mutate: vi.fn(),
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
})
