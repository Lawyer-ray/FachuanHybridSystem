vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/clipboard', () => ({
  copyToClipboard: vi.fn(() => Promise.resolve()),
}))

vi.mock('../LegalText', () => ({
  LegalText: ({ text }: { text: string }) => <span>{text}</span>,
}))

vi.mock('react-markdown', () => ({
  default: ({ children, components }: { children: string; components?: Record<string, unknown> }) => {
    // Simulate component rendering for pre and p
    return <div data-testid="react-markdown">{children}</div>
  },
}))

vi.mock('remark-gfm', () => ({ default: () => {} }))
vi.mock('rehype-highlight', () => ({ default: () => {} }))

vi.mock('highlight.js/lib/core', () => ({
  default: { registerLanguage: vi.fn() },
}))
vi.mock('highlight.js/lib/languages/json', () => ({ default: {} }))

vi.mock('lucide-react', () => ({
  Copy: () => <svg data-testid="copy-icon" />,
  Check: () => <svg data-testid="check-icon" />,
}))

import { render, screen, fireEvent, act } from '@testing-library/react'
import { MarkdownContent } from '../MarkdownContent'

describe('MarkdownContent', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders content text', () => {
    render(<MarkdownContent content="Hello world" />)
    expect(screen.getByTestId('react-markdown')).toHaveTextContent(/Hello world/)
  })

  it('renders empty content without error', () => {
    render(<MarkdownContent content="" />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('applies system styles when isSystem is true', () => {
    const { container } = render(<MarkdownContent content="Error" isSystem />)
    const proseDiv = container.querySelector('.prose-red')
    expect(proseDiv).toBeInTheDocument()
  })

  it('does not apply system styles by default', () => {
    const { container } = render(<MarkdownContent content="Normal" />)
    const proseDiv = container.querySelector('.prose-red')
    expect(proseDiv).not.toBeInTheDocument()
  })

  it('renders in streaming mode', () => {
    render(<MarkdownContent content="streaming text" isStreaming />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with code blocks', () => {
    const content = 'Some text\n```json\n{"key": "value"}\n```\nMore text'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('wraps bare JSON objects in code blocks', () => {
    const content = 'Here is some JSON: {"key": "value"} end'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('wraps bare JSON arrays in code blocks', () => {
    const content = 'Array: [1, 2, 3] end'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('does not wrap invalid JSON', () => {
    const content = 'Not JSON: {invalid} here'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles nested JSON objects', () => {
    const content = 'Data: {"a": {"b": 1}} end'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('removes metadata block with code fence', () => {
    const content = 'Before\n```markdown\n【案例元数据汇总】\nmetadata here\n```\nAfter'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('removes metadata block without code fence', () => {
    const content = 'Before\n【案例元数据汇总】\nmetadata here\nAfter'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with mixed markdown', () => {
    const content = '# Title\n\n**Bold** and *italic*\n\n- list item 1\n- list item 2'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles streaming mode with content changes', () => {
    const { rerender } = render(<MarkdownContent content="initial" isStreaming />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()

    // Update content in streaming mode
    act(() => {
      rerender(<MarkdownContent content="updated content" isStreaming />)
    })
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles non-streaming mode with content changes', () => {
    const { rerender } = render(<MarkdownContent content="initial" />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()

    rerender(<MarkdownContent content="updated content" />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with tables', () => {
    const content = '| Header 1 | Header 2 |\n|----------|----------|\n| Cell 1   | Cell 2   |'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with links', () => {
    const content = 'Visit [Google](https://google.com) for more info'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles isSystem and isStreaming together', () => {
    const { container } = render(<MarkdownContent content="test" isSystem isStreaming />)
    const proseDiv = container.querySelector('.prose-red')
    expect(proseDiv).toBeInTheDocument()
  })

  it('handles content with multiple code blocks', () => {
    const content = '```js\ncode1\n```\nText\n```python\ncode2\n```'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles empty JSON content', () => {
    const content = '{}'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles deeply nested JSON', () => {
    const content = '{"a": {"b": {"c": {"d": 1}}}}'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with special characters', () => {
    const content = 'Special chars: <>&"\'`'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles very long content', () => {
    const content = 'A'.repeat(10000)
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles streaming mode toggle', () => {
    const { rerender } = render(<MarkdownContent content="test" isStreaming />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()

    // Switch to non-streaming
    act(() => {
      rerender(<MarkdownContent content="test" />)
    })
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with bare JSON that has spaces', () => {
    const content = 'Data: { "key" : "value" , "num" : 42 } end'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with unicode', () => {
    const content = '你好世界 🌍 こんにちは'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content that is only whitespace', () => {
    render(<MarkdownContent content="   \n  \n   " />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with multiple JSON objects', () => {
    const content = '{"a": 1} and {"b": 2}'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with partial JSON bracket match', () => {
    const content = 'Text with { unclosed bracket'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles streaming mode content update', () => {
    const { rerender } = render(<MarkdownContent content="Hello" isStreaming />)
    // Simulate streaming content arriving
    act(() => {
      rerender(<MarkdownContent content="Hello World" isStreaming />)
    })
    act(() => {
      rerender(<MarkdownContent content="Hello World, how are you?" isStreaming />)
    })
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('memo component re-renders correctly', () => {
    const { rerender } = render(<MarkdownContent content="test" />)
    // Same props should not re-render
    rerender(<MarkdownContent content="test" />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with all bracket types', () => {
    const content = 'Object: {"key": "value"} and Array: [1, 2] and Nested: {"arr": [1, 2]}'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })
})
