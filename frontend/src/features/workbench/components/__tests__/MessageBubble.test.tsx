/**
 * MessageBubble Component Tests
 * 测试消息气泡组件
 */

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/date', () => ({
  formatDate: () => '2026-06-15',
}))

vi.mock('../stores/workbench-store', () => ({
  useWorkbenchStore: vi.fn(() => vi.fn(() => false)),
}))

vi.mock('../MarkdownContent', () => ({
  MarkdownContent: ({ content }: { content: string }) => <div data-testid="markdown">{content}</div>,
}))

vi.mock('../BatchItemContent', () => ({
  BatchItemContent: ({ content }: { content: string }) => <div data-testid="batch-item">{content}</div>,
}))

vi.mock('../InlineToolCalls', () => ({
  InlineToolCalls: () => <div data-testid="tool-calls" />,
}))

vi.mock('../AssistantMeta', () => ({
  AssistantMeta: () => <div data-testid="assistant-meta" />,
}))

vi.mock('../MessageActions', () => ({
  FeedbackButtons: () => <div data-testid="feedback" />,
  MessageActions: () => <div data-testid="message-actions" />,
}))

vi.mock('../BatchDownloadButton', () => ({
  BatchDownloadButton: () => <div data-testid="batch-download" />,
}))

vi.mock('../StreamingBubble', () => ({
  StreamingBubble: () => <div data-testid="streaming-bubble" />,
}))

vi.mock('../UserMessageContent', () => ({
  UserMessageContent: ({ message }: { message: { content: string } }) => <div data-testid="user-content">{message.content}</div>,
}))

import { render, screen } from '@testing-library/react'
import { MessageBubble } from '../MessageBubble'

const createMessage = (overrides: Record<string, unknown> = {}) => ({
  id: 1,
  role: 'assistant' as const,
  content: 'Test content',
  llm_model: '',
  tool_call_id: '',
  tool_name: '',
  tool_input: {},
  tool_output: {},
  metadata: {},
  created_at: '2026-06-15T10:00:00Z',
  ...overrides,
})

describe('MessageBubble', () => {
  it('renders user message with user content component', () => {
    render(<MessageBubble message={createMessage({ role: 'user', content: 'Hello' })} />)
    expect(screen.getByTestId('user-content')).toHaveTextContent('Hello')
  })

  it('renders assistant message with markdown content', () => {
    render(<MessageBubble message={createMessage({ role: 'assistant', content: 'Reply' })} />)
    expect(screen.getByTestId('markdown')).toHaveTextContent('Reply')
  })

  it('renders system message', () => {
    render(<MessageBubble message={createMessage({ role: 'system', content: 'System msg' })} />)
    expect(screen.getByTestId('markdown')).toHaveTextContent('System msg')
  })

  it('renders batch item content for batch_item source', () => {
    render(
      <MessageBubble
        message={createMessage({ metadata: { source: 'batch_item' } })}
      />,
    )
    expect(screen.getByTestId('batch-item')).toBeInTheDocument()
  })

  it('renders inline tool calls when provided', () => {
    const toolCall = createMessage({ id: 2, role: 'tool', tool_name: 'search' })
    render(
      <MessageBubble
        message={createMessage()}
        toolCalls={[toolCall as any]}
      />,
    )
    expect(screen.getByTestId('tool-calls')).toBeInTheDocument()
  })

  it('renders batch download button for batch_analysis source', () => {
    render(
      <MessageBubble
        message={createMessage({ metadata: { source: 'batch_analysis', job_id: 'job-1' } })}
      />,
    )
    expect(screen.getByTestId('batch-download')).toBeInTheDocument()
  })

  it('does not render batch download button for non-batch messages', () => {
    render(<MessageBubble message={createMessage()} />)
    expect(screen.queryByTestId('batch-download')).not.toBeInTheDocument()
  })

  it('renders timestamp', () => {
    render(<MessageBubble message={createMessage()} />)
    expect(screen.getByText('2026-06-15')).toBeInTheDocument()
  })
})
