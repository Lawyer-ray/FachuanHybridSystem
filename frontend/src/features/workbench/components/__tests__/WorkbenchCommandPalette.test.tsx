/**
 * WorkbenchCommandPalette Component Tests
 * 测试工作台命令面板组件
 */

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('../utils/export', () => ({
  exportToMarkdown: vi.fn(() => '# Exported'),
  downloadFile: vi.fn(),
}))

vi.mock('@/components/ui/command', () => ({
  CommandDialog: ({ children, open }: { children: React.ReactNode; open: boolean }) =>
    open ? <div data-testid="command-dialog">{children}</div> : null,
  CommandInput: ({ placeholder }: { placeholder: string }) => <input placeholder={placeholder} />,
  CommandEmpty: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  CommandGroup: ({ children, heading }: { children: React.ReactNode; heading: string }) => (
    <div data-testid={`group-${heading}`}>{children}</div>
  ),
  CommandItem: ({ children, onSelect, value }: { children: React.ReactNode; onSelect: () => void; value?: string }) => (
    <div data-testid={`item-${value}`} onClick={onSelect}>{children}</div>
  ),
  CommandSeparator: () => <hr />,
  CommandList: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}))

const mockSetSelectedAgent = vi.fn()
const mockSetSelectedModel = vi.fn()
const mockAbortStream = vi.fn()

vi.mock('../../stores/workbench-store', () => ({
  useWorkbenchStore: vi.fn((selector: (s: Record<string, unknown>) => unknown) => {
    const state: Record<string, unknown> = {
      setSelectedAgent: mockSetSelectedAgent,
      setSelectedModel: mockSetSelectedModel,
      abortStream: mockAbortStream,
      isStreaming: false,
      models: [{ id: 'gpt-4o', name: 'GPT-4o' }],
      messages: [{ id: 1, role: 'user', content: 'msg' }],
      currentSession: { id: 1, title: 'Test' },
    }
    return selector(state)
  }),
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { WorkbenchCommandPalette } from '../WorkbenchCommandPalette'
import { toast } from 'sonner'
import { downloadFile } from '../utils/export'

describe('WorkbenchCommandPalette', () => {
  const defaultProps = {
    open: true,
    onOpenChange: vi.fn(),
    onNewSession: vi.fn(),
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders when open is true', () => {
    render(<WorkbenchCommandPalette {...defaultProps} />)
    expect(screen.getByTestId('command-dialog')).toBeInTheDocument()
  })

  it('does not render when open is false', () => {
    render(<WorkbenchCommandPalette {...defaultProps} open={false} />)
    expect(screen.queryByTestId('command-dialog')).not.toBeInTheDocument()
  })

  it('renders session commands group', () => {
    render(<WorkbenchCommandPalette {...defaultProps} />)
    expect(screen.getByTestId('group-会话')).toBeInTheDocument()
  })

  it('renders agent commands group', () => {
    render(<WorkbenchCommandPalette {...defaultProps} />)
    expect(screen.getByTestId('group-切换助手')).toBeInTheDocument()
  })

  it('renders model commands group', () => {
    render(<WorkbenchCommandPalette {...defaultProps} />)
    expect(screen.getByTestId('group-切换模型')).toBeInTheDocument()
  })

  it('calls onNewSession when new session is selected', () => {
    const onNewSession = vi.fn()
    render(<WorkbenchCommandPalette {...defaultProps} onNewSession={onNewSession} />)
    fireEvent.click(screen.getByTestId('item-新建会话 new session'))
    expect(onNewSession).toHaveBeenCalled()
  })


  it('selects model and shows toast', () => {
    render(<WorkbenchCommandPalette {...defaultProps} />)
    fireEvent.click(screen.getByTestId('item-GPT-4o gpt-4o'))
    expect(toast.success).toHaveBeenCalled()
    expect(defaultProps.onOpenChange).toHaveBeenCalledWith(false)
  })
})
