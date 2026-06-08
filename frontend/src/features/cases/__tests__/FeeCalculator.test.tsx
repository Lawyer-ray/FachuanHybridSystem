import { render, screen, fireEvent } from '@testing-library/react'
import { FeeCalculator } from '../components/FeeCalculator'

vi.mock('lucide-react', () => ({
  Calculator: (props: Record<string, unknown>) => <svg data-testid="calculator-icon" {...props} />,
  Loader2: (props: Record<string, unknown>) => <svg data-testid="loader-icon" {...props} />,
}))

vi.mock('../hooks/use-reference-data', () => ({
  useCalculateFee: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    data: null,
    isError: false,
    error: null,
  })),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, ...props }: Record<string, unknown>) => <button {...props}>{children}</button>,
}))

vi.mock('@/components/ui/card', () => ({
  Card: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardContent: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardHeader: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
  CardTitle: ({ children, ...props }: Record<string, unknown>) => <div {...props}>{children}</div>,
}))

import { useCalculateFee } from '../hooks/use-reference-data'
const mockUseCalculateFee = vi.mocked(useCalculateFee)

describe('FeeCalculator', () => {
  beforeEach(() => {
    mockUseCalculateFee.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      data: null,
      isError: false,
      error: null,
    } as never)
  })

  it('renders default prompt text', () => {
    render(<FeeCalculator />)
    expect(screen.getByText('点击"计算"按钮获取诉讼费')).toBeInTheDocument()
  })

  it('renders calculate button', () => {
    render(<FeeCalculator />)
    expect(screen.getByText('计算')).toBeInTheDocument()
  })

  it('renders fee results when data is available', () => {
    mockUseCalculateFee.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      data: {
        show_acceptance_fee: true,
        acceptance_fee: 5000,
        show_half_fee: true,
        acceptance_fee_half: 2500,
      },
      isError: false,
      error: null,
    } as never)
    render(<FeeCalculator />)
    expect(screen.getByText('案件受理费')).toBeInTheDocument()
    expect(screen.getByText('案件受理费（减半）')).toBeInTheDocument()
  })

  it('renders error message on calculation failure', () => {
    mockUseCalculateFee.mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      data: null,
      isError: true,
      error: new Error('Network error'),
    } as never)
    render(<FeeCalculator />)
    expect(screen.getByText(/计算失败/)).toBeInTheDocument()
  })

  it('calls mutate when calculate button is clicked', () => {
    const mutate = vi.fn()
    mockUseCalculateFee.mockReturnValue({
      mutate,
      isPending: false,
      data: null,
      isError: false,
      error: null,
    } as never)
    render(<FeeCalculator targetAmount={100000} caseType="civil" />)
    fireEvent.click(screen.getByText('计算'))
    expect(mutate).toHaveBeenCalledWith({
      target_amount: 100000,
      preservation_amount: undefined,
      case_type: 'civil',
      cause_of_action: undefined,
    })
  })

  it('renders in embedded mode without card wrapper', () => {
    render(<FeeCalculator embedded />)
    expect(screen.getByText('诉讼费计算')).toBeInTheDocument()
    expect(screen.getByText('计算')).toBeInTheDocument()
  })

  it('renders card wrapper in non-embedded mode', () => {
    render(<FeeCalculator />)
    expect(screen.getByText('诉讼费计算')).toBeInTheDocument()
  })
})
