/**
 * MessageList Component Tests
 * 测试消息列表组件
 */

vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/components/ui/scroll-area', () => ({
  ScrollArea: React.forwardRef(({ children, className, ...props }: Record<string, unknown>, ref: React.Ref<HTMLDivElement>) => (
    <div ref={ref} data-testid="scroll-area" className={className as string} {...props}>{children}</div>
  )),
}))

vi.mock('../MessageBubble', () => ({
  MessageBubble: ({ message }: { message: { content: string; role: string } }) => (
    <div data-testid={`message-${message.role}`}>{message.content}</div>
  ),
  StreamingBubble: ({ message }: { message: { content: string } }) => (
    <div data-testid="streaming-bubble">{message.content}</div>
  ),
}))

const mockLoadOlderMessages = vi.fn()

vi.mock('../../stores/workbench-store', () => ({
  useWorkbenchStore: vi.fn((selector: (s: Record<string, unknown>) => unknown) => {
    const state: Record<string, unknown> = {
      messages: [],
      streamingMessage: null,
      isStreaming: false,
      messagesLoading: false,
      currentSession: null,
      hasMoreMessages: false,
      loadingOlder: false,
      loadOlderMessages: mockLoadOlderMessages,
    }
    return selector(state)
  }),
}))

import React from 'react'
import { render, screen } from '@testing-library/react'
import { MessageList } from '../MessageList'
import { useWorkbenchStore } from '../../stores/workbench-store'

describe('MessageList', () => {
  beforeEach(() => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state: Record<string, unknown> = {
        messages: [],
        streamingMessage: null,
        isStreaming: false,
        messagesLoading: false,
        currentSession: null,
        hasMoreMessages: false,
        loadingOlder: false,
        loadOlderMessages: mockLoadOlderMessages,
      }
      return selector(state)
    })
  })

  it('shows empty state when no messages', () => {
    render(<MessageList />)
    expect(screen.getByText('开始对话吧')).toBeInTheDocument()
  })

  it('shows loading skeleton when loading', () => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state: Record<string, unknown> = {
        messages: [],
        streamingMessage: null,
        isStreaming: false,
        messagesLoading: true,
        currentSession: null,
        hasMoreMessages: false,
        loadingOlder: false,
        loadOlderMessages: mockLoadOlderMessages,
      }
      return selector(state)
    })
    render(<MessageList />)
    // Skeleton renders 3 pulse elements
    const pulses = document.querySelectorAll('.animate-pulse')
    expect(pulses.length).toBeGreaterThan(0)
  })

  it('renders user and assistant messages', () => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state: Record<string, unknown> = {
        messages: [
          { id: 1, role: 'user', content: 'Hello', created_at: '2026-06-15T10:00:00Z' },
          { id: 2, role: 'assistant', content: 'Hi there', created_at: '2026-06-15T10:01:00Z' },
        ],
        streamingMessage: null,
        isStreaming: false,
        messagesLoading: false,
        currentSession: { id: 1, title: 'Test' },
        hasMoreMessages: false,
        loadingOlder: false,
        loadOlderMessages: mockLoadOlderMessages,
      }
      return selector(state)
    })
    render(<MessageList />)
    expect(screen.getByTestId('message-user')).toHaveTextContent('Hello')
    expect(screen.getByTestId('message-assistant')).toHaveTextContent('Hi there')
  })

  it('renders streaming bubble when streaming', () => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state: Record<string, unknown> = {
        messages: [
          { id: 1, role: 'user', content: 'Hello', created_at: '2026-06-15T10:00:00Z' },
        ],
        streamingMessage: { content: 'streaming...' },
        isStreaming: true,
        messagesLoading: false,
        currentSession: { id: 1, title: 'Test' },
        hasMoreMessages: false,
        loadingOlder: false,
        loadOlderMessages: mockLoadOlderMessages,
      }
      return selector(state)
    })
    render(<MessageList />)
    expect(screen.getByTestId('streaming-bubble')).toHaveTextContent('streaming...')
  })

  it('hides empty state during streaming', () => {
    vi.mocked(useWorkbenchStore).mockImplementation((selector: (s: Record<string, unknown>) => unknown) => {
      const state: Record<string, unknown> = {
        messages: [],
        streamingMessage: { content: '...' },
        isStreaming: true,
        messagesLoading: false,
        currentSession: { id: 1, title: 'Test' },
        hasMoreMessages: false,
        loadingOlder: false,
        loadOlderMessages: mockLoadOlderMessages,
      }
      return selector(state)
    })
    render(<MessageList />)
    expect(screen.queryByText('开始对话吧')).not.toBeInTheDocument()
  })
})
