/**
 * StreamingBubble Component Tests
 * 测试流式消息气泡组件
 */

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('../../stores/workbench-store', () => ({
  useWorkbenchStore: vi.fn((selector: (s: Record<string, unknown>) => unknown) => {
    const state: Record<string, unknown> = {
      reconnecting: false,
    }
    return selector(state)
  }),
}))

vi.mock('../MarkdownContent', () => ({
  MarkdownContent: ({ content, isStreaming }: { content: string; isStreaming?: boolean }) => (
    <div data-testid="markdown-content" data-streaming={isStreaming}>{content}</div>
  ),
}))

import { render, screen } from '@testing-library/react'
import { StreamingBubble } from '../StreamingBubble'
import { useWorkbenchStore } from '../../stores/workbench-store'
import type { StreamingMessage } from '../../types'

const createStreamingMessage = (overrides: Partial<StreamingMessage> = {}): StreamingMessage => ({
  content: '',
  currentActivity: null,
  toolCalls: [],
  handoffs: [],
  error: null,
  model: null,
  ...overrides,
})

describe('StreamingBubble', () => {
  beforeEach(() => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state: Record<string, unknown> = { reconnecting: false }
      return selector(state)
    })
  })


  it('renders content when provided', () => {
    render(<StreamingBubble message={createStreamingMessage({ content: 'Hello streaming' })} />)
    expect(screen.getByTestId('markdown-content')).toHaveTextContent('Hello streaming')
  })

  it('renders current activity indicator', () => {
    render(<StreamingBubble message={createStreamingMessage({ currentActivity: 'Searching...' })} />)
    expect(screen.getByText('Searching...')).toBeInTheDocument()
  })

  it('renders tool calls', () => {
    const message = createStreamingMessage({
      toolCalls: [{ toolCallId: 'tc1', name: 'search_case', status: 'running', input: {} }],
    })
    render(<StreamingBubble message={message} />)
    expect(screen.getByText('search_case')).toBeInTheDocument()
  })

  it('renders handoff badges', () => {
    const message = createStreamingMessage({
      handoffs: [{ from: 'triage', to: 'case' }],
    })
    render(<StreamingBubble message={message} />)
    expect(screen.getByText('triage')).toBeInTheDocument()
    expect(screen.getByText('case')).toBeInTheDocument()
  })

  it('renders error message', () => {
    const message = createStreamingMessage({ error: 'Connection timeout' })
    render(<StreamingBubble message={message} />)
    expect(screen.getByText('Connection timeout')).toBeInTheDocument()
  })

  it('renders model name when provided', () => {
    const message = createStreamingMessage({ model: 'gpt-4o' })
    render(<StreamingBubble message={message} />)
    expect(screen.getByText('gpt-4o')).toBeInTheDocument()
  })
})
