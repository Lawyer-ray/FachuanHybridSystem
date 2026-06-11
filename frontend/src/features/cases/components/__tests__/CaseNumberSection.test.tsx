import { render, screen, fireEvent, cleanup, act } from '@testing-library/react'
import { CaseNumberSection, type CaseNumberSectionRef } from '../CaseNumberSection'
import type { CaseNumber } from '../../types'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

const mockCreateMutate = vi.fn()
const mockUpdateMutate = vi.fn()
const mockDeleteMutate = vi.fn()

vi.mock('../../hooks/use-case-number-mutations', () => ({
  useCaseNumberMutations: () => ({
    createCaseNumber: { mutate: mockCreateMutate, isPending: false },
    updateCaseNumber: { mutate: mockUpdateMutate, isPending: false },
    deleteCaseNumber: { mutate: mockDeleteMutate, isPending: false },
  }),
}))

vi.mock('@/lib/date', () => ({
  formatDateOnly: (v: string | null) => v ?? '-',
}))

vi.mock('@/lib/format', () => ({
  formatAmountInt: (v: number | null) => (v != null ? `¥${v}` : '-'),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))
vi.mock('@/components/ui/input', () => ({
  Input: (props: Record<string, unknown>) => <input {...props} />,
}))
vi.mock('@/components/ui/label', () => ({
  Label: ({ children }: { children: React.ReactNode }) => <label>{children}</label>,
}))
vi.mock('@/components/ui/switch', () => ({
  Switch: (props: Record<string, unknown>) => <input type="checkbox" {...props} />,
}))
vi.mock('@/components/ui/select', () => ({
  Select: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectItem: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  SelectValue: ({ children }: { children: React.ReactNode }) => <span>{children}</span>,
}))
vi.mock('@/components/ui/dialog', () => ({
  Dialog: ({ children, open }: { children: React.ReactNode; open?: boolean }) =>
    open === false ? null : <div data-testid="dialog">{children}</div>,
  DialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  DialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogAction: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
  AlertDialogTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))
vi.mock('@/components/ui/collapsible', () => ({
  Collapsible: ({ children }: { children: React.ReactNode }) => <div data-testid="collapsible">{children}</div>,
  CollapsibleContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CollapsibleTrigger: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('lucide-react', () => ({
  Hash: (p: Record<string, unknown>) => <svg data-testid="hash" {...p} />,
  Trash2: (p: Record<string, unknown>) => <svg data-testid="trash" {...p} />,
  Loader2: (p: Record<string, unknown>) => <svg data-testid="loader" {...p} />,
  ChevronDown: (p: Record<string, unknown>) => <svg data-testid="chevron-down" {...p} />,
  ChevronUp: (p: Record<string, unknown>) => <svg data-testid="chevron-up" {...p} />,
  Pencil: (p: Record<string, unknown>) => <svg data-testid="pencil" {...p} />,
  Scale: (p: Record<string, unknown>) => <svg data-testid="scale" {...p} />,
}))

function makeCaseNumber(overrides: Partial<CaseNumber> = {}): CaseNumber {
  return {
    id: 1,
    number: '(2025)京01民初123号',
    document_name: '民事判决书',
    remarks: '一审判决',
    is_active: true,
    execution_cutoff_date: null,
    execution_paid_amount: 0,
    execution_use_deduction_order: false,
    execution_year_days: 360,
    execution_date_inclusion: 'both',
    execution_manual_text: '',
    ...overrides,
  } as unknown as CaseNumber
}

describe('CaseNumberSection', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  // -- Non-editable rendering --

  it('renders empty message when no case numbers and not editable', () => {
    render(<CaseNumberSection caseNumbers={[]} />)
    expect(screen.getByText('暂无案号')).toBeInTheDocument()
  })

  it('renders empty message when empty and editable without caseId', () => {
    render(<CaseNumberSection caseNumbers={[]} editable />)
    expect(screen.getByText('暂无案号')).toBeInTheDocument()
  })

  it('renders case number text', () => {
    const cn = makeCaseNumber()
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.getByText('(2025)京01民初123号')).toBeInTheDocument()
  })

  it('renders document name in parentheses', () => {
    const cn = makeCaseNumber()
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.getByText('(民事判决书)')).toBeInTheDocument()
  })

  it('renders remarks', () => {
    const cn = makeCaseNumber()
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.getByText('一审判决')).toBeInTheDocument()
  })

  it('renders active indicator (green dot)', () => {
    const cn = makeCaseNumber({ is_active: true })
    render(<CaseNumberSection caseNumbers={[cn]} />)
    const dot = document.querySelector('.bg-green-500')
    expect(dot).toBeInTheDocument()
  })

  it('renders inactive indicator', () => {
    const cn = makeCaseNumber({ is_active: false })
    render(<CaseNumberSection caseNumbers={[cn]} />)
    const dot = document.querySelector('.bg-muted-foreground\\/30')
    expect(dot).toBeInTheDocument()
  })

  it('does not render document_name when null', () => {
    const cn = makeCaseNumber({ document_name: null })
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.getByText('(2025)京01民初123号')).toBeInTheDocument()
    expect(screen.queryByText('(民事判决书)')).not.toBeInTheDocument()
  })

  it('does not render remarks when empty', () => {
    const cn = makeCaseNumber({ remarks: '' })
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.queryByText('一审判决')).not.toBeInTheDocument()
  })

  // -- Execution parameters --

  it('shows execution parameters toggle when has execution data', () => {
    const cn = makeCaseNumber({
      execution_cutoff_date: '2025-06-01',
      execution_paid_amount: 1000,
    })
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.getByText('执行参数')).toBeInTheDocument()
  })

  it('does not show execution parameters toggle when no execution data', () => {
    const cn = makeCaseNumber()
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.queryByText('执行参数')).not.toBeInTheDocument()
  })

  it('shows execution cutoff date', () => {
    const cn = makeCaseNumber({
      execution_cutoff_date: '2025-06-01',
      execution_paid_amount: 0,
      execution_manual_text: '',
    })
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.getByText('利息截止日：')).toBeInTheDocument()
  })

  it('shows execution paid amount when > 0', () => {
    const cn = makeCaseNumber({
      execution_paid_amount: 5000,
      execution_cutoff_date: '2025-01-01',
      execution_manual_text: '',
    })
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.getByText('已付金额：')).toBeInTheDocument()
  })

  it('shows execution year days = 0 as actual days', () => {
    const cn = makeCaseNumber({
      execution_cutoff_date: '2025-01-01',
      execution_year_days: 0,
    })
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.getByText('执行参数')).toBeInTheDocument()
  })

  it('shows execution year days != 0 as days count', () => {
    const cn = makeCaseNumber({
      execution_cutoff_date: '2025-01-01',
      execution_year_days: 365,
    })
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.getByText('执行参数')).toBeInTheDocument()
  })

  it('shows execution date inclusion label', () => {
    const cn = makeCaseNumber({
      execution_cutoff_date: '2025-01-01',
      execution_date_inclusion: 'start',
    })
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.getByText('执行参数')).toBeInTheDocument()
  })

  it('shows manual text when present', () => {
    const cn = makeCaseNumber({
      execution_cutoff_date: '2025-01-01',
      execution_manual_text: '手动文本内容',
    })
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.getByText('执行参数')).toBeInTheDocument()
  })

  // -- Editable mode --

  it('renders edit and delete buttons in editable mode', () => {
    const cn = makeCaseNumber()
    render(<CaseNumberSection caseNumbers={[cn]} editable caseId={1} />)
    expect(screen.getByTestId('pencil')).toBeInTheDocument()
    expect(screen.getByTestId('trash')).toBeInTheDocument()
  })

  it('does not render edit buttons when not editable', () => {
    const cn = makeCaseNumber()
    render(<CaseNumberSection caseNumbers={[cn]} />)
    expect(screen.queryByTestId('pencil')).not.toBeInTheDocument()
  })

  it('does not render edit buttons when caseId is missing', () => {
    const cn = makeCaseNumber()
    render(<CaseNumberSection caseNumbers={[cn]} editable />)
    expect(screen.queryByTestId('pencil')).not.toBeInTheDocument()
  })

  // -- Multiple case numbers --

  it('renders multiple case numbers', () => {
    const numbers = [
      makeCaseNumber({ id: 1, number: '案号1' }),
      makeCaseNumber({ id: 2, number: '案号2', document_name: null, remarks: '', is_active: false }),
    ]
    render(<CaseNumberSection caseNumbers={numbers} />)
    expect(screen.getByText('案号1')).toBeInTheDocument()
    expect(screen.getByText('案号2')).toBeInTheDocument()
  })

  // -- Ref API --

  it('exposes openAdd via ref', () => {
    const ref = { current: null as CaseNumberSectionRef | null }
    render(<CaseNumberSection caseNumbers={[]} editable caseId={1} ref={ref} />)
    expect(ref.current).not.toBeNull()
    expect(typeof ref.current!.openAdd).toBe('function')
  })

  it('opens add dialog via ref.openAdd', () => {
    const ref = { current: null as CaseNumberSectionRef | null }
    render(<CaseNumberSection caseNumbers={[]} editable caseId={1} ref={ref} />)
    act(() => { ref.current!.openAdd() })
    expect(screen.getByText('添加案号')).toBeInTheDocument()
  })

  // -- Default export --

  it('has a default export', async () => {
    const mod = await import('../CaseNumberSection')
    expect(mod.default).toBe(mod.CaseNumberSection)
  })
})
