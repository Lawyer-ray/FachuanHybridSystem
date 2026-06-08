/**
 * UserMessageContent Component Tests
 * 测试用户消息内容组件（支持编辑重发）
 */

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/components/ui/textarea', () => ({
  Textarea: ({ value, onChange, onKeyDown, className, ...props }: Record<string, unknown>) => (
    <textarea
      data-testid="edit-textarea"
      value={value as string}
      onChange={onChange as React.ChangeEventHandler<HTMLTextAreaElement>}
      onKeyDown={onKeyDown as React.KeyboardEventHandler<HTMLTextAreaElement>}
      className={className as string}
      {...props}
    />
  ),
}))

const mockEditAndResend = vi.fn()

vi.mock('../../stores/workbench-store', () => ({
  useWorkbenchStore: vi.fn((selector: (s: Record<string, unknown>) => unknown) => {
    const state: Record<string, unknown> = {
      editAndResend: mockEditAndResend,
      isStreaming: false,
    }
    return selector(state)
  }),
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { UserMessageContent } from '../UserMessageContent'

const createMessage = (overrides: Record<string, unknown> = {}) => ({
  id: 1,
  role: 'user' as const,
  content: 'Hello world',
  llm_model: '',
  tool_call_id: '',
  tool_name: '',
  tool_input: {},
  tool_output: {},
  metadata: {},
  created_at: '2026-06-15T10:00:00Z',
  ...overrides,
})

describe('UserMessageContent', () => {
  it('renders message content in display mode', () => {
    render(<UserMessageContent message={createMessage() as any} />)
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('shows edit button on hover (hidden by default via group-hover)', () => {
    render(<UserMessageContent message={createMessage() as any} />)
    const editBtn = screen.getByTitle('编辑并重发')
    expect(editBtn).toBeInTheDocument()
    expect(editBtn.className).toContain('hidden')
  })

  it('enters edit mode when edit button is clicked', () => {
    render(<UserMessageContent message={createMessage() as any} />)
    fireEvent.click(screen.getByTitle('编辑并重发'))
    expect(screen.getByTestId('edit-textarea')).toBeInTheDocument()
    expect(screen.getByText('取消')).toBeInTheDocument()
    expect(screen.getByText('重发')).toBeInTheDocument()
  })

  it('cancels edit mode and restores original content', () => {
    render(<UserMessageContent message={createMessage() as any} />)
    fireEvent.click(screen.getByTitle('编辑并重发'))
    fireEvent.click(screen.getByText('取消'))
    expect(screen.queryByTestId('edit-textarea')).not.toBeInTheDocument()
    expect(screen.getByText('Hello world')).toBeInTheDocument()
  })

  it('calls editAndResend when saving with changed content', () => {
    render(<UserMessageContent message={createMessage() as any} />)
    fireEvent.click(screen.getByTitle('编辑并重发'))
    const textarea = screen.getByTestId('edit-textarea')
    fireEvent.change(textarea, { target: { value: 'Updated message' } })
    fireEvent.click(screen.getByText('重发'))
    expect(mockEditAndResend).toHaveBeenCalledWith(1, 'Updated message')
  })

})
