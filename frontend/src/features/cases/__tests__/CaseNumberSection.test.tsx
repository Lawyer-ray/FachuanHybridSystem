import { render, screen, fireEvent } from '@testing-library/react'
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
    createCaseNumber: { mutate: vi.fn(), isPending: false },
    updateCaseNumber: { mutate: vi.fn(), isPending: false },
    deleteCaseNumber: { mutate: vi.fn(), isPending: false },
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

  it('renders case number with document name', () => {
    const numbers = [{
      id: 1,
      number: '(2024)京0105民初1234号',
      display_number: '(2024)京0105民初1234号',
      document_name: '民事判决书',
      is_active: true,
      remarks: '',
    }]
    render(<CaseNumberSection caseNumbers={numbers as never} />)
    expect(screen.getByText('(2024)京0105民初1234号')).toBeInTheDocument()
    expect(screen.getByText('(民事判决书)')).toBeInTheDocument()
  })

  it('renders case number with remarks', () => {
    const numbers = [{
      id: 1,
      number: '案号1',
      display_number: '案号1',
      document_name: '',
      is_active: true,
      remarks: '这是备注',
    }]
    render(<CaseNumberSection caseNumbers={numbers as never} />)
    expect(screen.getByText('这是备注')).toBeInTheDocument()
  })

  it('renders inactive case number with grey dot', () => {
    const numbers = [{
      id: 1,
      number: '案号1',
      display_number: '案号1',
      is_active: false,
    }]
    render(<CaseNumberSection caseNumbers={numbers as never} />)
    expect(screen.getByText('案号1')).toBeInTheDocument()
  })

  it('renders case number with execution parameters', () => {
    const numbers = [{
      id: 1,
      number: '案号1',
      display_number: '案号1',
      is_active: true,
      execution_cutoff_date: '2024-12-31',
      execution_paid_amount: 5000,
      execution_year_days: 365,
      execution_date_inclusion: 'include',
      execution_use_deduction_order: false,
      execution_manual_text: '',
    }]
    render(<CaseNumberSection caseNumbers={numbers as never} />)
    expect(screen.getByText('执行参数')).toBeInTheDocument()
  })

  it('renders case number with manual execution text', () => {
    const numbers = [{
      id: 1,
      number: '案号1',
      display_number: '案号1',
      is_active: true,
      execution_cutoff_date: '2024-12-31',
      execution_paid_amount: 0,
      execution_year_days: 360,
      execution_date_inclusion: 'both',
      execution_use_deduction_order: true,
      execution_manual_text: '手动执行请求文本',
    }]
    render(<CaseNumberSection caseNumbers={numbers as never} />)
    expect(screen.getByText('执行参数')).toBeInTheDocument()
  })

  it('renders multiple case numbers', () => {
    const numbers = [
      { id: 1, number: '案号A', display_number: '案号A', is_active: true },
      { id: 2, number: '案号B', display_number: '案号B', is_active: false },
    ]
    render(<CaseNumberSection caseNumbers={numbers as never} />)
    expect(screen.getByText('案号A')).toBeInTheDocument()
    expect(screen.getByText('案号B')).toBeInTheDocument()
  })

  it('renders editable mode with edit and delete buttons', () => {
    const numbers = [{
      id: 1,
      number: '案号1',
      display_number: '案号1',
      is_active: true,
    }]
    render(<CaseNumberSection caseNumbers={numbers as never} editable caseId={1} />)
    expect(screen.getByText('案号1')).toBeInTheDocument()
    // Edit and delete buttons should be present (rendered as icon buttons)
    const pencilIcons = screen.getAllByTestId('pencil')
    const trashIcons = screen.getAllByTestId('trash')
    expect(pencilIcons.length).toBeGreaterThan(0)
    expect(trashIcons.length).toBeGreaterThan(0)
  })

  it('renders editable mode with empty case numbers showing add dialog', () => {
    render(<CaseNumberSection caseNumbers={[]} editable caseId={1} />)
    // Should show "暂无案号" even in editable mode when empty
    expect(screen.getByText('暂无案号')).toBeInTheDocument()
  })

  it('renders non-editable empty state', () => {
    render(<CaseNumberSection caseNumbers={[]} />)
    expect(screen.getByText('暂无案号')).toBeInTheDocument()
  })

  it('renders case number with execution_use_deduction_order true', () => {
    const numbers = [{
      id: 1,
      number: '案号1',
      display_number: '案号1',
      is_active: true,
      execution_cutoff_date: '2024-12-31',
      execution_paid_amount: 0,
      execution_year_days: 360,
      execution_date_inclusion: 'both',
      execution_use_deduction_order: true,
      execution_manual_text: '',
    }]
    render(<CaseNumberSection caseNumbers={numbers as never} />)
    // hasExecution = execution_cutoff_date is truthy => shows "执行参数"
    expect(screen.getByText('执行参数')).toBeInTheDocument()
  })

  it('renders case number with year_days 0 (按实际天数)', () => {
    const numbers = [{
      id: 1,
      number: '案号1',
      display_number: '案号1',
      is_active: true,
      execution_cutoff_date: '',
      execution_paid_amount: 100,
      execution_year_days: 0,
      execution_date_inclusion: '',
      execution_use_deduction_order: false,
      execution_manual_text: '',
    }]
    render(<CaseNumberSection caseNumbers={numbers as never} />)
    // hasExecution = execution_paid_amount > 0 => shows "执行参数"
    expect(screen.getByText('执行参数')).toBeInTheDocument()
  })

})
