import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { VoiceButton } from '../VoiceButton'

// Mock Tooltip components that use ResizeObserver
vi.mock('@/components/ui/tooltip', () => ({
  Tooltip: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TooltipTrigger: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
  TooltipContent: ({ children }: React.PropsWithChildren) => <div>{children}</div>,
}))

describe('VoiceButton', () => {
  it('renders nothing when not supported', () => {
    const { container } = render(
      <VoiceButton isSupported={false} isListening={false} onStart={vi.fn()} onStop={vi.fn()} />,
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders mic button when supported and not listening', () => {
    render(
      <VoiceButton isSupported={true} isListening={false} onStart={vi.fn()} onStop={vi.fn()} />,
    )
    expect(screen.getByRole('button')).toBeInTheDocument()
  })

  it('calls onStart when clicking while not listening', async () => {
    const onStart = vi.fn()
    const user = userEvent.setup()
    render(
      <VoiceButton isSupported={true} isListening={false} onStart={onStart} onStop={vi.fn()} />,
    )
    await user.click(screen.getByRole('button'))
    expect(onStart).toHaveBeenCalledTimes(1)
  })

  it('calls onStop when clicking while listening', async () => {
    const onStop = vi.fn()
    const user = userEvent.setup()
    render(
      <VoiceButton isSupported={true} isListening={true} onStart={vi.fn()} onStop={onStop} />,
    )
    await user.click(screen.getByRole('button'))
    expect(onStop).toHaveBeenCalledTimes(1)
  })

  it('disables button when disabled prop is true', () => {
    render(
      <VoiceButton isSupported={true} isListening={false} onStart={vi.fn()} onStop={vi.fn()} disabled />,
    )
    expect(screen.getByRole('button')).toBeDisabled()
  })
})
