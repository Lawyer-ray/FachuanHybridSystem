import { render, screen, fireEvent } from '@testing-library/react'
import { QuoteCreateDialog } from '../components/QuoteCreateDialog'

vi.mock('lucide-react', () => ({
  Loader2: () => <svg data-testid="loader" />,
}))

vi.mock('../schemas', () => ({
  quoteCreateSchema: {},
}))

const mockCreateQuoteMutate = vi.fn()

vi.mock('../hooks/use-quote-mutations', () => ({
  useCreateQuote: () => ({
    mutate: mockCreateQuoteMutate,
    isPending: false,
    isError: false,
  }),
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

vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))

vi.mock('@hookform/resolvers/zod', () => ({ zodResolver: () => ({}) }))

vi.mock('react-hook-form', async () => {
  const actual = await vi.importActual('react-hook-form')
  return {
    ...actual,
    useForm: () => ({
      control: {},
      handleSubmit: (fn: Function) => (e: Event) => { e.preventDefault(); fn({}) },
      reset: vi.fn(),
      watch: vi.fn(() => undefined),
      formState: { errors: {} },
    }),
  }
})

describe('QuoteCreateDialog', () => {

  it('does not render when closed', () => {
    render(<QuoteCreateDialog open={false} onOpenChange={vi.fn()} />)
    expect(screen.queryByText('创建财产保全询价')).not.toBeInTheDocument()
  })

  it('renders create button', () => {
    render(<QuoteCreateDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByText('创建询价')).toBeInTheDocument()
  })

  it('renders cancel button', () => {
    render(<QuoteCreateDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByText('取消')).toBeInTheDocument()
  })

  // ===== Branch coverage: dialog description =====

  it('renders description text', () => {
    render(<QuoteCreateDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByText('填写以下信息创建新的财产保全询价任务')).toBeInTheDocument()
  })

  // ===== Branch coverage: cancel calls onOpenChange(false) =====

  it('calls onOpenChange(false) on cancel', () => {
    const onOpenChange = vi.fn()
    render(<QuoteCreateDialog open={true} onOpenChange={onOpenChange} />)
    fireEvent.click(screen.getByText('取消'))
    expect(onOpenChange).toHaveBeenCalledWith(false)
  })

  // ===== Branch coverage: form submission (via mock) =====

  it('renders form element', () => {
    render(<QuoteCreateDialog open={true} onOpenChange={vi.fn()} />)
    const formEl = document.querySelector('form')
    expect(formEl).not.toBeNull()
  })

  // ===== Branch coverage: custom options =====

  it('renders with custom corpOptions', () => {
    const corpOptions = [{ value: 'c1', label: 'Custom Corp' }]
    render(<QuoteCreateDialog open={true} onOpenChange={vi.fn()} corpOptions={corpOptions} />)
    expect(screen.getByText('创建询价')).toBeInTheDocument()
  })

  it('renders with custom categoryOptions', () => {
    const categoryOptions = [{ value: 'cat1', label: 'Custom Category' }]
    render(<QuoteCreateDialog open={true} onOpenChange={vi.fn()} categoryOptions={categoryOptions} />)
    expect(screen.getByText('创建询价')).toBeInTheDocument()
  })

  it('renders with custom credentialOptions', () => {
    const credentialOptions = [{ value: 99, label: 'Custom Credential' }]
    render(<QuoteCreateDialog open={true} onOpenChange={vi.fn()} credentialOptions={credentialOptions} />)
    expect(screen.getByText('创建询价')).toBeInTheDocument()
  })

  // ===== Branch coverage: form field labels =====

  it('renders form field labels', () => {
    render(<QuoteCreateDialog open={true} onOpenChange={vi.fn()} />)
    expect(screen.getByText(/保全金额/)).toBeInTheDocument()
  })

})
