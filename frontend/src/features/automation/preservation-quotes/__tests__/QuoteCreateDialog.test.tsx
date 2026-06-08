import { render, screen } from '@testing-library/react'
import { QuoteCreateDialog } from '../components/QuoteCreateDialog'

vi.mock('lucide-react', () => ({
  Loader2: () => <svg data-testid="loader" />,
}))

vi.mock('../schemas', () => ({
  quoteCreateSchema: {},
}))

vi.mock('../hooks/use-quote-mutations', () => ({
  useCreateQuote: () => ({
    mutate: vi.fn(),
    isPending: false,
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

})
