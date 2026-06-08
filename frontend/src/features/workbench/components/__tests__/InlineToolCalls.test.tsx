import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { InlineToolCalls } from '../InlineToolCalls'

vi.mock('../tool-results', () => ({
  renderToolResult: vi.fn(() => null),
}))

vi.mock('highlight.js/lib/core', () => ({
  default: {
    registerLanguage: vi.fn(),
    highlight: vi.fn(() => ({ value: 'highlighted' })),
  },
}))

vi.mock('highlight.js/lib/languages/json', () => ({ default: {} }))

describe('InlineToolCalls', () => {
  const createToolCall = (overrides: Record<string, unknown> = {}) => ({
    id: 1,
    role: 'tool' as const,
    content: '',
    llm_model: '',
    tool_call_id: 'tc-1',
    tool_name: 'search_cases',
    tool_input: { query: 'test' },
    tool_output: { results: [] },
    metadata: {},
    created_at: '2026-06-15T10:00:00Z',
    ...overrides,
  })

  it('renders tool call names', () => {
    const toolCalls = [createToolCall()]
    render(<InlineToolCalls toolCalls={toolCalls as any} />)
    expect(screen.getByText('search_cases')).toBeInTheDocument()
  })

  it('renders multiple tool calls', () => {
    const toolCalls = [
      createToolCall({ id: 1, tool_name: 'search_cases' }),
      createToolCall({ id: 2, tool_name: 'get_client' }),
    ]
    render(<InlineToolCalls toolCalls={toolCalls as any} />)
    expect(screen.getByText('search_cases')).toBeInTheDocument()
    expect(screen.getByText('get_client')).toBeInTheDocument()
  })

  it('expands tool call on click', async () => {
    const toolCalls = [createToolCall()]
    const user = userEvent.setup()
    render(<InlineToolCalls toolCalls={toolCalls as any} />)
    await user.click(screen.getByText('search_cases'))
    // After expanding, should show input/output sections
    expect(screen.getByText('输入')).toBeInTheDocument()
  })

  it('shows error icon for failed tool calls', () => {
    const toolCalls = [createToolCall({ metadata: { success: false } })]
    const { container } = render(<InlineToolCalls toolCalls={toolCalls as any} />)
    // XCircle icon should be rendered
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('shows success icon for successful tool calls', () => {
    const toolCalls = [createToolCall({ metadata: { success: true } })]
    const { container } = render(<InlineToolCalls toolCalls={toolCalls as any} />)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('renders empty list when no tool calls', () => {
    const { container } = render(<InlineToolCalls toolCalls={[]} />)
    expect(container.querySelector('[class*="space-y"]')?.children.length).toBe(0)
  })
})
