/**
 * LprCalculatorTool Component Tests
 * 测试 利息/违约金计算器组件
 */

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/clipboard', () => ({
  copyToClipboard: vi.fn(() => Promise.resolve()),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../../hooks/use-lpr-rates', () => ({
  useLprRates: vi.fn(),
}))

vi.mock('../../hooks/use-lpr-calculate', () => ({
  useLprCalculate: vi.fn(),
}))

vi.mock('@/components/ui/button', () => ({
  Button: ({ children, onClick, disabled, variant, size, className }: Record<string, unknown>) => (
    <button onClick={onClick as React.MouseEventHandler} disabled={disabled as boolean} className={className as string}>{children}</button>
  ),
}))

vi.mock('@/components/ui/input', () => ({
  Input: ({ value, onChange, placeholder, type, id, className, ...props }: Record<string, unknown>) => (
    <input
      id={id as string}
      type={type as string}
      value={value as string}
      onChange={onChange as React.ChangeEventHandler}
      placeholder={placeholder as string}
      className={className as string}
      {...props}
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
import { useLprRates } from '../../hooks/use-lpr-rates'
import { useLprCalculate } from '../../hooks/use-lpr-calculate'

describe('LprCalculatorTool', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useLprRates).mockReturnValue({
      data: [
        { id: 1, rate_type: '1y', effective_date: '2024-10-21', rate: '3.10' },
        { id: 2, rate_type: '5y', effective_date: '2024-10-21', rate: '3.60' },
      ],
      isLoading: false,
    } as any)
    vi.mocked(useLprCalculate).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
      data: null,
    } as any)
  })

  it('renders page title', () => {
    render(<LprCalculatorTool />)
    expect(screen.getByText('利息/违约金计算器')).toBeInTheDocument()
  })

  
  it('renders rate mode options', () => {
    render(<LprCalculatorTool />)
    expect(screen.getByText('LPR 利率')).toBeInTheDocument()
    expect(screen.getByText('自定义利率')).toBeInTheDocument()
    expect(screen.getByText('迟延履行利率')).toBeInTheDocument()
  })

  it('renders calculate button', () => {
    render(<LprCalculatorTool />)
    expect(screen.getByText('计算利息')).toBeInTheDocument()
  })

  
  })
