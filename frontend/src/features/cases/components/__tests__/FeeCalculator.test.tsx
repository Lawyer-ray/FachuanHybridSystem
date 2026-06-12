import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { FeeCalculator, type FeeCalculatorProps } from '../FeeCalculator'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

const mockMutate = vi.fn()
vi.mock('../../hooks/use-reference-data', () => ({
  useCalculateFee: () => ({
    mutate: mockMutate,
    isPending: false,
    data: null,
    isError: false,
    error: null,
  }),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...p }: Record<string, unknown>) => <button {...p}>{children}</button>,
}))
vi.mock('@/components/ui/card', () => ({
  Card: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CardTitle: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

vi.mock('lucide-react', () => ({
  Calculator: (p: Record<string, unknown>) => <svg data-testid="calculator" {...p} />,
  Loader2: (p: Record<string, unknown>) => <svg data-testid="loader" {...p} />,
}))

function renderFeeCalculator(props: Partial<FeeCalculatorProps> = {}) {
  return render(<FeeCalculator {...props} />)
}

describe('FeeCalculator', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  it('renders in embedded mode', () => {
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('诉讼费计算')).toBeInTheDocument()
    expect(screen.getByText('计算')).toBeInTheDocument()
    expect(screen.getByText('点击"计算"按钮获取诉讼费')).toBeInTheDocument()
  })

  it('renders in card mode by default', () => {
    renderFeeCalculator()
    expect(screen.getAllByText('诉讼费计算').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('计算').length).toBeGreaterThanOrEqual(1)
  })

  it('calls calculateFee.mutate with all params on click', () => {
    renderFeeCalculator({
      targetAmount: 100000,
      preservationAmount: 50000,
      caseType: 'civil',
      causeOfAction: 'contract',
      embedded: true,
    })
    fireEvent.click(screen.getByText('计算'))
    expect(mockMutate).toHaveBeenCalledWith({
      target_amount: 100000,
      preservation_amount: 50000,
      case_type: 'civil',
      cause_of_action: 'contract',
    })
  })

  it('uses undefined for null amounts', () => {
    renderFeeCalculator({ targetAmount: null, preservationAmount: null, embedded: true })
    fireEvent.click(screen.getByText('计算'))
    expect(mockMutate).toHaveBeenCalledWith({
      target_amount: undefined,
      preservation_amount: undefined,
      case_type: undefined,
      cause_of_action: undefined,
    })
  })

  it('uses undefined for missing props', () => {
    renderFeeCalculator({ embedded: true })
    fireEvent.click(screen.getByText('计算'))
    expect(mockMutate).toHaveBeenCalledWith({
      target_amount: undefined,
      preservation_amount: undefined,
      case_type: undefined,
      cause_of_action: undefined,
    })
  })

  it('handles causeOfAction as null', () => {
    renderFeeCalculator({ causeOfAction: null, embedded: true })
    fireEvent.click(screen.getByText('计算'))
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ cause_of_action: undefined }),
    )
  })

  // Test the embedded branch with a defined but falsy targetAmount
  it('passes 0 as target_amount when targetAmount is 0', () => {
    renderFeeCalculator({ targetAmount: 0, embedded: true })
    fireEvent.click(screen.getByText('计算'))
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ target_amount: 0 }),
    )
  })

  // Default export
  it('has a default export', async () => {
    const mod = await import('../FeeCalculator')
    expect(mod.default).toBe(mod.FeeCalculator)
  })
})
