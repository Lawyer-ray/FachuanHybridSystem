/**
 * MessageActions Component Tests
 * 测试消息操作按钮组件
 */

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/clipboard', () => ({
  copyToClipboard: vi.fn(),
}))

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}))

const mockSubmitFeedback = vi.fn()
const mockSendMessage = vi.fn()
const mockSetQuotedContent = vi.fn()

vi.mock('../../stores/workbench-store', () => ({
  useWorkbenchStore: vi.fn((selector: (s: Record<string, unknown>) => unknown) => {
    const state: Record<string, unknown> = {
      submitFeedback: mockSubmitFeedback,
      sendMessage: mockSendMessage,
      setQuotedContent: mockSetQuotedContent,
      isStreaming: false,
      messages: [
        { id: 1, role: 'user', content: 'user msg' },
        { id: 2, role: 'assistant', content: 'assistant reply' },
      ],
    }
    return selector(state)
  }),
}))

import { render, screen, fireEvent } from '@testing-library/react'
import { FeedbackButtons, MessageActions } from '../MessageActions'
import { copyToClipboard } from '@/lib/clipboard'
import { toast } from 'sonner'

const createMessage = (overrides: Record<string, unknown> = {}) => ({
  id: 2,
  role: 'assistant' as const,
  content: 'Test assistant content',
  llm_model: '',
  tool_call_id: '',
  tool_name: '',
  tool_input: {},
  tool_output: {},
  metadata: {},
  created_at: '2026-06-15T10:00:00Z',
  ...overrides,
})

describe('FeedbackButtons', () => {
  it('renders thumbs up and down buttons', () => {
    render(<FeedbackButtons message={createMessage() as any} />)
    expect(screen.getByTitle('有帮助')).toBeInTheDocument()
    expect(screen.getByTitle('没帮助')).toBeInTheDocument()
  })

  it('calls submitFeedback with good rating on thumbs up click', () => {
    render(<FeedbackButtons message={createMessage() as any} />)
    fireEvent.click(screen.getByTitle('有帮助'))
    expect(mockSubmitFeedback).toHaveBeenCalledWith(2, 'good')
  })

  it('calls submitFeedback with bad rating on thumbs down click', () => {
    render(<FeedbackButtons message={createMessage() as any} />)
    fireEvent.click(screen.getByTitle('没帮助'))
    expect(mockSubmitFeedback).toHaveBeenCalledWith(2, 'bad')
  })

  it('shows active state for existing good feedback', () => {
    const msg = createMessage({ metadata: { feedback: { rating: 'good' } } })
    render(<FeedbackButtons message={msg as any} />)
    const btn = screen.getByTitle('有帮助')
    expect(btn.className).toContain('text-green-500')
  })
})

describe('MessageActions', () => {
  it('renders copy, quote, and regenerate buttons', () => {
    render(<MessageActions message={createMessage() as any} />)
    expect(screen.getByTitle('复制')).toBeInTheDocument()
    expect(screen.getByTitle('引用')).toBeInTheDocument()
    expect(screen.getByTitle('重新生成')).toBeInTheDocument()
  })

  it('copies message content on copy click', () => {
    render(<MessageActions message={createMessage() as any} />)
    fireEvent.click(screen.getByTitle('复制'))
    expect(copyToClipboard).toHaveBeenCalledWith('Test assistant content')
  })

  it('sets quoted content on quote click', () => {
    render(<MessageActions message={createMessage() as any} />)
    fireEvent.click(screen.getByTitle('引用'))
    expect(mockSetQuotedContent).toHaveBeenCalledWith('Test assistant content')
    expect(toast.success).toHaveBeenCalledWith('已引用，可在输入框中查看')
  })

  it('sends previous user message on regenerate click', () => {
    render(<MessageActions message={createMessage() as any} />)
    fireEvent.click(screen.getByTitle('重新生成'))
    expect(mockSendMessage).toHaveBeenCalledWith('user msg')
  })
})
