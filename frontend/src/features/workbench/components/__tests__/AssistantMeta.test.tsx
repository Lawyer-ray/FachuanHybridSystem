import { render, screen } from '@testing-library/react'
import { AssistantMeta } from '../AssistantMeta'

describe('AssistantMeta', () => {
  const createMessage = (overrides: Record<string, unknown> = {}) => ({
    id: 1,
    role: 'assistant' as const,
    content: 'test',
    llm_model: 'gpt-4o',
    tool_call_id: '',
    tool_name: '',
    tool_input: {},
    tool_output: {},
    metadata: {},
    created_at: '2026-06-15T10:00:00Z',
    ...overrides,
  })

  it('renders nothing when no tokens and no model', () => {
    const message = createMessage({ llm_model: '', metadata: {} })
    const { container } = render(<AssistantMeta message={message as any} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders model name when provided', () => {
    const message = createMessage()
    render(<AssistantMeta message={message as any} />)
    expect(screen.getByText('gpt-4o')).toBeInTheDocument()
  })

  it('renders token usage when metadata has tokens', () => {
    const message = createMessage({
      metadata: { tokens: { prompt: 100, completion: 50, total: 150 } },
    })
    render(<AssistantMeta message={message as any} />)
    expect(screen.getByText(/输入 100/)).toBeInTheDocument()
    expect(screen.getByText(/输出 50/)).toBeInTheDocument()
    expect(screen.getByText(/共 150 tokens/)).toBeInTheDocument()
  })

  it('renders duration when provided', () => {
    const message = createMessage({
      metadata: { tokens: { prompt: 100, completion: 50, total: 150 }, duration_ms: 2500 },
    })
    render(<AssistantMeta message={message as any} />)
    expect(screen.getByText(/2500ms/)).toBeInTheDocument()
  })

  it('renders tokens with zero values', () => {
    const message = createMessage({
      metadata: { tokens: { prompt: 0, completion: 0, total: 0 } },
    })
    render(<AssistantMeta message={message as any} />)
    expect(screen.getByText(/共 0 tokens/)).toBeInTheDocument()
  })

  it('renders model name without tokens', () => {
    const message = createMessage({ metadata: {} })
    render(<AssistantMeta message={message as any} />)
    expect(screen.getByText('gpt-4o')).toBeInTheDocument()
  })
})
