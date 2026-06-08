import { render, screen } from '@testing-library/react'
import { CaseNumberSection } from '../components/CaseNumberSection'

vi.mock('lucide-react', () => ({
  Hash: () => <svg data-testid="hash" />,
  Trash2: () => <svg data-testid="trash" />,
  Loader2: () => <svg data-testid="loader" />,
  ChevronDown: () => <svg data-testid="chevron-down" />,
  ChevronUp: () => <svg data-testid="chevron-up" />,
  Pencil: () => <svg data-testid="pencil" />,
  Scale: () => <svg data-testid="scale" />,
}))

vi.mock('@tanstack/react-query', () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

vi.mock('@/lib/date', () => ({ formatDateOnly: (d: string) => d ?? '' }))
vi.mock('@/lib/format', () => ({ formatAmountInt: (v: number) => `${v}` }))

vi.mock('../hooks/use-case-number-mutations', () => ({
  useCaseNumberMutations: () => ({
    createNumber: { mutate: vi.fn(), isPending: false },
    updateNumber: { mutate: vi.fn(), isPending: false },
    deleteNumber: { mutate: vi.fn(), isPending: false },
  }),
}))

vi.mock('../types', () => ({
  YEAR_DAYS_CHOICES: [{ value: '360', label: '360天' }],
  DATE_INCLUSION_CHOICES: [{ value: 'include', label: '包含' }],
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))
vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))
vi.mock('@/components/ui/label', () => ({
  Label: ({ children, ...props }: Record<string, unknown>) => <label {...props}>{children}</label>,
}))
vi.mock('@/components/ui/switch', () => ({
  Switch: (props: Record<string, unknown>) => <input type="checkbox" {...props} />,
}))
vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: () => <span />,
}))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/collapsible', () => ({
  Collapsible: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CollapsibleContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CollapsibleTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

describe('CaseNumberSection', () => {
  it('renders empty state when no case numbers', () => {
    render(<CaseNumberSection caseNumbers={[]} />)
    expect(screen.getByText('暂无案号')).toBeInTheDocument()
  })

  it('renders case number data', () => {
    const numbers = [{
      id: 1,
      number: '(2024)京0105民初1234号',
      display_number: '(2024)京0105民初1234号',
      year_days: '365',
      date_inclusion: 'include',
    }]
    render(<CaseNumberSection caseNumbers={numbers as never} />)
    expect(screen.getByText('(2024)京0105民初1234号')).toBeInTheDocument()
  })

  it('renders hash icon for each number', () => {
    const numbers = [{
      id: 1,
      number: '案号1',
      display_number: '案号1',
    }]
    render(<CaseNumberSection caseNumbers={numbers as never} />)
    expect(screen.getByTestId('hash')).toBeInTheDocument()
  })

  it('renders with empty caseNumbers array', () => {
    const { container } = render(<CaseNumberSection caseNumbers={[]} />)
    expect(container).toBeTruthy()
  })

})
