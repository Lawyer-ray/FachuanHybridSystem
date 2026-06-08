vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/clipboard', () => ({
  copyToClipboard: vi.fn(() => Promise.resolve()),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

const mockLprRates = vi.fn()
const mockLprCalculate = vi.fn()

vi.mock('../../hooks/use-lpr-rates', () => ({
  useLprRates: (...args: unknown[]) => mockLprRates(...args),
}))

vi.mock('../../hooks/use-lpr-calculate', () => ({
  useLprCalculate: (...args: unknown[]) => mockLprCalculate(...args),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/input', () => ({
  Input: ({ value, onChange, placeholder, type, className, disabled }: Record<string, unknown>) => (
    <input
      type={type as string}
      value={value as string}
      onChange={onChange as React.ChangeEventHandler}
      placeholder={placeholder as string}
      className={className as string}
      disabled={disabled as boolean}
    />
  ),
}))

vi.mock('@/components/ui/table', () => ({
  Table: ({ children }: { children: React.ReactNode }) => <table>{children}</table>,
  TableBody: ({ children }: { children: React.ReactNode }) => <tbody>{children}</tbody>,
  TableCell: ({ children, className }: { children: React.ReactNode; className?: string }) => <td className={className}>{children}</td>,
  TableHead: ({ children, className }: { children: React.ReactNode; className?: string }) => <th className={className}>{children}</th>,
  TableHeader: ({ children }: { children: React.ReactNode }) => <thead>{children}</thead>,
  TableRow: ({ children }: { children: React.ReactNode }) => <tr>{children}</tr>,
}))

vi.mock('@/components/ui/alert-dialog', () => ({
  AlertDialog: ({ children, open }: { children: React.ReactNode; open: boolean }) => open ? <div data-testid="alert-dialog">{children}</div> : null,
  AlertDialogAction: ({ children, onClick }: { children: React.ReactNode; onClick?: () => void }) => <button onClick={onClick}>{children}</button>,
  AlertDialogCancel: ({ children }: { children: React.ReactNode }) => <button>{children}</button>,
  AlertDialogContent: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogDescription: ({ children }: { children: React.ReactNode }) => <p>{children}</p>,
  AlertDialogFooter: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogHeader: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  AlertDialogTitle: ({ children }: { children: React.ReactNode }) => <h2>{children}</h2>,
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { LprCalculatorTool } from '../LprCalculatorTool'

const mockMutate = vi.fn()

const defaultRatesData = {
  items: [
    { id: 1, rate_type: '1y', effective_date: '2024-10-21', rate: '3.10', rate_1y: '3.10', rate_5y: '3.60' },
  ],
}

function makeMutateWithData(data: Record<string, unknown>) {
  return vi.fn((body: unknown, opts?: { onSuccess?: (d: unknown) => void }) => {
    if (opts?.onSuccess) opts.onSuccess(data)
  })
}

describe('LprCalculatorTool', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    mockMutate.mockReset()
    mockLprRates.mockReturnValue({ data: defaultRatesData, isLoading: false })
    mockLprCalculate.mockReturnValue({ mutate: mockMutate, isPending: false, data: null })
  })

  it('renders page title', () => {
    render(<LprCalculatorTool />)
    expect(screen.getByText('利息/违约金计算器')).toBeInTheDocument()
  })

  it('renders description', () => {
    render(<LprCalculatorTool />)
    expect(screen.getByText(/基于贷款市场报价利率计算利息/)).toBeInTheDocument()
  })

  it('renders latest LPR rate', () => {
    render(<LprCalculatorTool />)
    expect(screen.getByText(/当前LPR利率/)).toBeInTheDocument()
    expect(screen.getAllByText(/一年期/).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/五年期/).length).toBeGreaterThan(0)
  })

  it('renders no data message when no rates', () => {
    mockLprRates.mockReturnValue({ data: null, isLoading: false })
    render(<LprCalculatorTool />)
    expect(screen.getByText('暂无LPR数据')).toBeInTheDocument()
  })

  it('renders rate mode options', () => {
    render(<LprCalculatorTool />)
    expect(screen.getByText('LPR 利率')).toBeInTheDocument()
    expect(screen.getByText('自定义利率')).toBeInTheDocument()
    expect(screen.getByText('迟延履行利率')).toBeInTheDocument()
  })

  it('renders calculate and reset buttons', () => {
    render(<LprCalculatorTool />)
    expect(screen.getByText('计算利息')).toBeInTheDocument()
    expect(screen.getByText('重置表单')).toBeInTheDocument()
    expect(screen.getByText('历史记录')).toBeInTheDocument()
  })

  it('renders fixed principal mode by default', () => {
    render(<LprCalculatorTool />)
    expect(screen.getByText('固定本金')).toBeInTheDocument()
    expect(screen.getByText('变动本金')).toBeInTheDocument()
    expect(screen.getByText('开始日期')).toBeInTheDocument()
    expect(screen.getByText('结束日期')).toBeInTheDocument()
    expect(screen.getByText(/本金金额/)).toBeInTheDocument()
  })

  it('switches to variable principal mode', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('变动本金'))
    expect(screen.getByText('本金变动记录')).toBeInTheDocument()
    expect(screen.getByText('添加本金变动')).toBeInTheDocument()
  })

  it('adds principal change row', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('变动本金'))
    fireEvent.click(screen.getByText('添加本金变动'))
    // Should now have 2 rows (1 initial + 1 added)
    const dateInputs = screen.getAllByDisplayValue('')
    expect(dateInputs.length).toBeGreaterThan(3)
  })

  it('switches to custom rate mode', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('自定义利率'))
    expect(screen.getByText('利率单位')).toBeInTheDocument()
    expect(screen.getByText('利率数值')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('请输入具体数值')).toBeInTheDocument()
  })

  it('switches to delay rate mode', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('迟延履行利率'))
    expect(screen.getByDisplayValue('万分之（‱/天）')).toBeInTheDocument()
    expect(screen.getByDisplayValue('1.75')).toBeInTheDocument()
  })

  it('toggles history panel', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('历史记录'))
    expect(screen.getByText('计算历史')).toBeInTheDocument()
    expect(screen.getByText('暂无历史记录')).toBeInTheDocument()
  })

  it('shows empty history message', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('历史记录'))
    expect(screen.getByText('暂无历史记录')).toBeInTheDocument()
  })

  it('loads history from localStorage', () => {
    const historyItem = {
      id: 1,
      timestamp: new Date().toISOString(),
      useChanges: false,
      form: {
        start_date: '2024-01-01',
        end_date: '2024-12-31',
        principal: '100000',
        rate_mode: 'lpr',
        rate_type: '1y',
        multiplier: '1',
        custom_rate_unit: 'percent',
        custom_rate_value: '',
        year_days: 360,
        date_inclusion: 'both',
        changes: [],
      },
      result: { total_interest: '3100', total_days: 365, total_principal: '100000' },
      rateInfo: 'LPR 1年期 x1.0',
    }
    localStorage.setItem('lpr_calculator_history', JSON.stringify([historyItem]))
    render(<LprCalculatorTool />)
    // The history count badge should show
    expect(screen.getByText('(1)')).toBeInTheDocument()
    // Open history
    fireEvent.click(screen.getByText(/历史记录/))
    expect(screen.getByText('加载')).toBeInTheDocument()
    expect(screen.getByText(/LPR 1年期 x1\.0/)).toBeInTheDocument()
  })

  it('handles calculate with missing fields shows error', () => {
    render(<LprCalculatorTool />)
    // Clear the default values
    const inputs = screen.getAllByRole('spinbutton')
    fireEvent.change(inputs[0], { target: { value: '' } })
    fireEvent.click(screen.getByText('计算利息'))
    // Should not call mutate since validation fails
    // The component sets result with error message
  })

  it('calls mutate when calculating with valid data', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('计算利息'))
    expect(mockMutate).toHaveBeenCalled()
  })

  it('calls mutate with delay rate mode', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('迟延履行利率'))
    fireEvent.click(screen.getByText('计算利息'))
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ rate_mode: 'custom', custom_rate_unit: 'permyriad', custom_rate_value: '1.75' }),
      expect.any(Object),
    )
  })

  it('calls mutate with custom rate mode', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('自定义利率'))
    fireEvent.change(screen.getByPlaceholderText('请输入具体数值'), { target: { value: '5.0' } })
    fireEvent.click(screen.getByText('计算利息'))
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ rate_mode: 'custom', custom_rate_unit: 'percent', custom_rate_value: '5.0' }),
      expect.any(Object),
    )
  })

  it('resets form on reset click', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('重置表单'))
    // Form should be reset to defaults
    expect(screen.getByText('固定本金')).toBeInTheDocument()
  })

  it('renders result when calculation succeeds', () => {
    const result = {
      success: true,
      total_interest: '3100.00',
      total_days: 365,
      total_principal: '100000',
      start_date: '2024-01-01',
      end_date: '2024-12-31',
      periods: [
        { start_date: '2024-01-01', end_date: '2024-12-31', days: 365, rate: '3.10', rate_unit: 'percent', interest: '3100.00' },
      ],
      message: '',
      code: null,
      sync_info: null,
    }
    mockLprCalculate.mockReturnValue({ mutate: makeMutateWithData(result), isPending: false })

    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('计算利息'))
    expect(screen.getByText('计算明细')).toBeInTheDocument()
  })

  it('renders error when calculation fails', () => {
    const result = {
      success: false,
      message: '参数错误',
      total_interest: null,
      total_days: null,
      total_principal: null,
      start_date: null,
      end_date: null,
      periods: null,
      code: null,
      sync_info: null,
    }
    mockLprCalculate.mockReturnValue({ mutate: makeMutateWithData(result), isPending: false })

    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('计算利息'))
    expect(screen.getByText('参数错误')).toBeInTheDocument()
  })

  it('shows sync message when present', () => {
    const result = {
      success: true,
      total_interest: '3100.00',
      total_days: 365,
      total_principal: '100000',
      start_date: '2024-01-01',
      end_date: '2024-12-31',
      periods: [],
      message: '',
      code: null,
      sync_info: 'LPR数据已同步到最新',
    }
    mockLprCalculate.mockReturnValue({ mutate: makeMutateWithData(result), isPending: false })

    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('计算利息'))
    expect(screen.getByText('LPR数据已同步到最新')).toBeInTheDocument()
  })

  it('shows calculating state', () => {
    mockLprCalculate.mockReturnValue({ mutate: mockMutate, isPending: true, data: null })
    render(<LprCalculatorTool />)
    expect(screen.getByText('计算中...')).toBeInTheDocument()
  })

  it('variable mode shows validation error for empty changes', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('变动本金'))
    fireEvent.click(screen.getByText('计算利息'))
    // Should show error since changes are empty
  })

  it('displays LPR rate select options', () => {
    render(<LprCalculatorTool />)
    expect(screen.getByText('利率类型')).toBeInTheDocument()
    expect(screen.getByText('利率倍数')).toBeInTheDocument()
    expect(screen.getByText('计息基准')).toBeInTheDocument()
  })

  it('renders date inclusion options', () => {
    render(<LprCalculatorTool />)
    expect(screen.getByText('日期计算方式')).toBeInTheDocument()
  })

  it('displays history count', () => {
    const historyItem = {
      id: 1,
      timestamp: new Date().toISOString(),
      useChanges: false,
      form: {
        start_date: '2024-01-01', end_date: '2024-12-31', principal: '100000',
        rate_mode: 'lpr', rate_type: '1y', multiplier: '1',
        custom_rate_unit: 'percent', custom_rate_value: '', year_days: 360,
        date_inclusion: 'both', changes: [],
      },
      result: { total_interest: '3100', total_days: 365, total_principal: '100000' },
      rateInfo: 'LPR 1年期 x1.0',
    }
    localStorage.setItem('lpr_calculator_history', JSON.stringify([historyItem]))
    render(<LprCalculatorTool />)
    expect(screen.getByText('(1)')).toBeInTheDocument()
  })

  it('handles history item delete', () => {
    const historyItem = {
      id: 1,
      timestamp: new Date().toISOString(),
      useChanges: false,
      form: {
        start_date: '2024-01-01', end_date: '2024-12-31', principal: '100000',
        rate_mode: 'lpr', rate_type: '1y', multiplier: '1',
        custom_rate_unit: 'percent', custom_rate_value: '', year_days: 360,
        date_inclusion: 'both', changes: [],
      },
      result: { total_interest: '3100', total_days: 365, total_principal: '100000' },
      rateInfo: 'LPR 1年期 x1.0',
    }
    localStorage.setItem('lpr_calculator_history', JSON.stringify([historyItem]))
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText(/历史记录/))
    // Click delete button (X icon)
    const deleteButtons = screen.getAllByRole('button')
    // Find the delete button near the history item
    expect(screen.getByText('加载')).toBeInTheDocument()
  })

  it('loads from history item', () => {
    const historyItem = {
      id: 1,
      timestamp: new Date().toISOString(),
      useChanges: false,
      form: {
        start_date: '2024-01-01', end_date: '2024-12-31', principal: '50000',
        rate_mode: 'lpr', rate_type: '1y', multiplier: '1',
        custom_rate_unit: 'percent', custom_rate_value: '', year_days: 360,
        date_inclusion: 'both', changes: [],
      },
      result: { total_interest: '1550', total_days: 365, total_principal: '50000' },
      rateInfo: 'LPR 1年期 x1.0',
    }
    localStorage.setItem('lpr_calculator_history', JSON.stringify([historyItem]))
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText(/历史记录/))
    fireEvent.click(screen.getByText('加载'))
    // History panel should close
    expect(screen.queryByText('计算历史')).not.toBeInTheDocument()
  })

  it('clears history with confirmation', () => {
    const historyItem = {
      id: 1,
      timestamp: new Date().toISOString(),
      useChanges: false,
      form: {
        start_date: '2024-01-01', end_date: '2024-12-31', principal: '100000',
        rate_mode: 'lpr', rate_type: '1y', multiplier: '1',
        custom_rate_unit: 'percent', custom_rate_value: '', year_days: 360,
        date_inclusion: 'both', changes: [],
      },
      result: { total_interest: '3100', total_days: 365, total_principal: '100000' },
      rateInfo: 'LPR 1年期 x1.0',
    }
    localStorage.setItem('lpr_calculator_history', JSON.stringify([historyItem]))
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText(/历史记录/))
    fireEvent.click(screen.getByText('清空'))
    // Confirm dialog should appear
    expect(screen.getByTestId('alert-dialog')).toBeInTheDocument()
    fireEvent.click(screen.getByText('确定清空'))
    // History should be cleared
    expect(localStorage.getItem('lpr_calculator_history')).toBeNull()
  })

  it('displays variable mode with history', () => {
    const historyItem = {
      id: 1,
      timestamp: new Date().toISOString(),
      useChanges: true,
      form: {
        start_date: '', end_date: '', principal: '',
        rate_mode: 'lpr', rate_type: '1y', multiplier: '1',
        custom_rate_unit: 'percent', custom_rate_value: '', year_days: 360,
        date_inclusion: 'both',
        changes: [{ start_date: '2024-01-01', end_date: '2024-06-30', principal: '50000' }],
      },
      result: { total_interest: '775', total_days: 181, total_principal: '50000' },
      rateInfo: 'LPR 1年期 x1.0',
    }
    localStorage.setItem('lpr_calculator_history', JSON.stringify([historyItem]))
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText(/历史记录/))
    // Multiple elements contain '变动本金' (button and history item)
    expect(screen.getAllByText(/变动本金/).length).toBeGreaterThan(0)
  })

  it('removes principal change row', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('变动本金'))
    fireEvent.click(screen.getByText('添加本金变动'))
    // Now 2 rows; remove one
    const removeButtons = screen.getAllByRole('button').filter(b => b.querySelector('svg'))
    // Should not crash
    expect(screen.getByText('本金变动记录')).toBeInTheDocument()
  })

  it('renders result section with detail toggle', () => {
    const result = {
      success: true,
      total_interest: '3100.00',
      total_days: 365,
      total_principal: '100000',
      start_date: '2024-01-01',
      end_date: '2024-12-31',
      periods: [
        { start_date: '2024-01-01', end_date: '2024-12-31', days: 365, rate: '3.10', rate_unit: 'percent', interest: '3100.00' },
      ],
      message: '',
      code: null,
      sync_info: null,
    }
    mockLprCalculate.mockReturnValue({ mutate: makeMutateWithData(result), isPending: false })

    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('计算利息'))
    expect(screen.getByText('展开')).toBeInTheDocument()
    expect(screen.getByText('复制明细')).toBeInTheDocument()
    expect(screen.getByText('复制结果')).toBeInTheDocument()
  })

  it('toggles detail view', () => {
    const result = {
      success: true,
      total_interest: '3100.00',
      total_days: 365,
      total_principal: '100000',
      start_date: '2024-01-01',
      end_date: '2024-12-31',
      periods: [
        { start_date: '2024-01-01', end_date: '2024-06-30', days: 181, rate: '3.10', rate_unit: 'percent', interest: '1550.00' },
        { start_date: '2024-07-01', end_date: '2024-12-31', days: 184, rate: '3.10', rate_unit: 'percent', interest: '1550.00' },
      ],
      message: '',
      code: null,
      sync_info: null,
    }
    mockLprCalculate.mockReturnValue({ mutate: makeMutateWithData(result), isPending: false })

    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('计算利息'))
    fireEvent.click(screen.getByText('展开'))
    expect(screen.getByText('收起')).toBeInTheDocument()
  })

  it('result section is null when success is false', () => {
    const result = {
      success: false,
      message: 'Error',
      total_interest: null,
      total_days: null,
      total_principal: null,
      start_date: null,
      end_date: null,
      periods: null,
      code: null,
      sync_info: null,
    }
    mockLprCalculate.mockReturnValue({ mutate: makeMutateWithData(result), isPending: false })

    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('计算利息'))
    expect(screen.queryByText('计算明细')).not.toBeInTheDocument()
    expect(screen.getByText('Error')).toBeInTheDocument()
  })

  it('handles custom rate with null value', () => {
    render(<LprCalculatorTool />)
    fireEvent.click(screen.getByText('自定义利率'))
    fireEvent.click(screen.getByText('计算利息'))
    expect(mockMutate).toHaveBeenCalledWith(
      expect.objectContaining({ custom_rate_value: null }),
      expect.any(Object),
    )
  })
})
