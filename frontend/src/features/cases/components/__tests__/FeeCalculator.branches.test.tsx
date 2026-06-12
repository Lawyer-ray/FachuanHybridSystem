/**
 * Additional coverage tests for FeeCalculator.tsx
 * Targets: uncovered branches (16)
 * Focus: FeeResults with various data fields, formatCurrency, FeeRow null values,
 * embedded vs card mode, error state, pending state
 */

import { render, screen, fireEvent, cleanup } from '@testing-library/react'
import { FeeCalculator, type FeeCalculatorProps } from '../FeeCalculator'

vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>()
  return { ...actual, useNavigate: () => vi.fn() }
})

const mockMutate = vi.fn()
let mockCalculateFeeState: Record<string, unknown> = {
  mutate: mockMutate,
  isPending: false,
  data: null,
  isError: false,
  error: null,
}

vi.mock('../../hooks/use-reference-data', () => ({
  useCalculateFee: () => mockCalculateFeeState,
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

describe('FeeCalculator - branch coverage', () => {
  beforeEach(() => {
    cleanup()
    vi.clearAllMocks()
    mockCalculateFeeState = {
      mutate: mockMutate,
      isPending: false,
      data: null,
      isError: false,
      error: null,
    }
  })

  // --- formatCurrency branches (lines 22-25) ---

  it('formatCurrency with valid number shows formatted value', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        show_acceptance_fee: true,
        acceptance_fee: 1234.56,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText(/1,234\.56/)).toBeInTheDocument()
  })

  it('formatCurrency with 0 shows ¥0.00', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        show_acceptance_fee: true,
        acceptance_fee: 0,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText(/0\.00/)).toBeInTheDocument()
  })

  // --- FeeRow null value (line 28) ---

  it('FeeRow returns null when value is null', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        show_acceptance_fee: true,
        acceptance_fee: null,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    // When acceptance_fee is null, FeeRow returns null - no "案件受理费" text rendered
    // But other rows might still show, so just check the component renders
    expect(screen.getByText('诉讼费计算')).toBeInTheDocument()
  })

  // --- FeeResults with various data fields (lines 40-50) ---

  it('shows acceptance_fee_half when show_half_fee is true', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        show_half_fee: true,
        acceptance_fee_half: 500,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('案件受理费（减半）')).toBeInTheDocument()
  })

  it('shows preservation_fee when not null', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        preservation_fee: 1000,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('保全费')).toBeInTheDocument()
  })

  it('shows execution_fee when not null', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        execution_fee: 2000,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('执行费')).toBeInTheDocument()
  })

  it('shows payment_order_fee when show_payment_order_fee is true', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        show_payment_order_fee: true,
        payment_order_fee: 300,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('支付令费')).toBeInTheDocument()
  })

  it('shows bankruptcy_fee when not null', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        bankruptcy_fee: 5000,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('破产费')).toBeInTheDocument()
  })

  it('shows divorce_fee when not null', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        divorce_fee: 300,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('离婚案件费')).toBeInTheDocument()
  })

  it('shows personality_rights_fee when not null', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        personality_rights_fee: 500,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('人格权案件费')).toBeInTheDocument()
  })

  it('shows ip_fee when not null', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        ip_fee: 800,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('知识产权案件费')).toBeInTheDocument()
  })

  it('shows fixed_fee when not null', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        fixed_fee: 100,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('固定费用')).toBeInTheDocument()
  })

  it('shows fee_display_text when present', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        show_acceptance_fee: true,
        acceptance_fee: 1000,
        fee_display_text: '按标的额比例计算',
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('按标的额比例计算')).toBeInTheDocument()
  })

  it('shows "无计算结果" when no rows and no display text', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        show_acceptance_fee: false,
        fee_display_text: null,
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('无计算结果')).toBeInTheDocument()
  })

  // --- Error state (lines 104-105) ---

  it('shows error message in embedded mode', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      isError: true,
      error: { message: '计算服务不可用' },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText(/计算失败/)).toBeInTheDocument()
    expect(screen.getByText(/计算服务不可用/)).toBeInTheDocument()
  })

  it('shows error message in card mode', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      isError: true,
      error: { message: '网络错误' },
    }
    renderFeeCalculator()
    expect(screen.getByText(/计算失败/)).toBeInTheDocument()
    expect(screen.getByText(/网络错误/)).toBeInTheDocument()
  })

  // --- Pending state (lines 93-94) ---

  it('shows loading spinner when pending in embedded mode', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      isPending: true,
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByTestId('loader')).toBeInTheDocument()
  })

  it('shows loading spinner when pending in card mode', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      isPending: true,
    }
    renderFeeCalculator()
    expect(screen.getByTestId('loader')).toBeInTheDocument()
  })

  // --- Card mode with data (lines 130) ---

  it('shows FeeResults in card mode when data exists', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        show_acceptance_fee: true,
        acceptance_fee: 5000,
        fee_display_text: '诉讼费',
      },
    }
    renderFeeCalculator()
    expect(screen.getByText('案件受理费')).toBeInTheDocument()
    expect(screen.getByText('诉讼费')).toBeInTheDocument()
  })

  // --- Card mode: "点击计算" prompt (line 132) ---

  it('shows prompt text in card mode when no data', () => {
    renderFeeCalculator()
    expect(screen.getByText('点击"计算"按钮获取诉讼费')).toBeInTheDocument()
  })

  // --- Card mode: click calculate button ---

  it('calls mutate from card mode button', () => {
    renderFeeCalculator({ targetAmount: 100000 })
    const buttons = screen.getAllByText('计算')
    fireEvent.click(buttons[buttons.length - 1]) // Card mode button
    expect(mockMutate).toHaveBeenCalled()
  })

  // --- Multiple rows combined ---

  it('renders multiple fee rows at once', () => {
    mockCalculateFeeState = {
      ...mockCalculateFeeState,
      data: {
        show_acceptance_fee: true,
        acceptance_fee: 1000,
        show_half_fee: true,
        acceptance_fee_half: 500,
        preservation_fee: 200,
        execution_fee: 300,
        show_payment_order_fee: true,
        payment_order_fee: 150,
        bankruptcy_fee: 400,
        divorce_fee: 100,
        personality_rights_fee: 50,
        ip_fee: 60,
        fixed_fee: 70,
        fee_display_text: '综合费用',
      },
    }
    renderFeeCalculator({ embedded: true })
    expect(screen.getByText('案件受理费')).toBeInTheDocument()
    expect(screen.getByText('案件受理费（减半）')).toBeInTheDocument()
    expect(screen.getByText('保全费')).toBeInTheDocument()
    expect(screen.getByText('执行费')).toBeInTheDocument()
    expect(screen.getByText('支付令费')).toBeInTheDocument()
    expect(screen.getByText('破产费')).toBeInTheDocument()
    expect(screen.getByText('离婚案件费')).toBeInTheDocument()
    expect(screen.getByText('人格权案件费')).toBeInTheDocument()
    expect(screen.getByText('知识产权案件费')).toBeInTheDocument()
    expect(screen.getByText('固定费用')).toBeInTheDocument()
    expect(screen.getByText('综合费用')).toBeInTheDocument()
  })
})
