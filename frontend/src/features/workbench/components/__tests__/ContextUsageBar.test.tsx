/**
 * ContextUsageBar Component Tests
 * 测试上下文用量指示器组件
 */

vi.mock('../../hooks/use-context-usage', () => ({
  useContextUsage: vi.fn(),
  formatTokens: vi.fn((n: number) => {
    if (n >= 1000) return `${(n / 1000).toFixed(1)}K`
    return String(n)
  }),
}))

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    warning: vi.fn(),
  },
}))

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/components/ui/progress', () => ({
  Progress: ({ value }: { value: number }) => <div data-testid="progress" data-value={value} />,
}))

import { render, screen } from '@testing-library/react'
import { ContextUsageBar } from '../ContextUsageBar'
import { useContextUsage } from '../../hooks/use-context-usage'

const mockUseContextUsage = useContextUsage as ReturnType<typeof vi.fn>

describe('ContextUsageBar', () => {
  it('renders nothing when contextWindow is 0', () => {
    mockUseContextUsage.mockReturnValue({
      percent: 0,
      usedTokens: 0,
      contextWindow: 0,
      messageCount: 0,
    })
    const { container } = render(<ContextUsageBar />)
    expect(container.innerHTML).toBe('')
  })

  it('renders nothing when messageCount is 0', () => {
    mockUseContextUsage.mockReturnValue({
      percent: 0,
      usedTokens: 0,
      contextWindow: 8000,
      messageCount: 0,
    })
    const { container } = render(<ContextUsageBar />)
    expect(container.innerHTML).toBe('')
  })

  it('renders progress bar and token counts', () => {
    mockUseContextUsage.mockReturnValue({
      percent: 25,
      usedTokens: 2000,
      contextWindow: 8000,
      messageCount: 5,
    })
    render(<ContextUsageBar />)
    expect(screen.getByTestId('progress')).toBeInTheDocument()
    expect(screen.getByText(/2\.0K/)).toBeInTheDocument()
    expect(screen.getByText(/8\.0K/)).toBeInTheDocument()
  })

  it('renders with green color for low usage', () => {
    mockUseContextUsage.mockReturnValue({
      percent: 25,
      usedTokens: 2000,
      contextWindow: 8000,
      messageCount: 5,
    })
    const { container } = render(<ContextUsageBar />)
    expect(container.querySelector('.text-green-600, .dark\\:text-green-400')).toBeTruthy()
  })
})
