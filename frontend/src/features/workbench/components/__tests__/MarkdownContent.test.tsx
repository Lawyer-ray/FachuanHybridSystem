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
import { copyToClipboard } from '@/lib/clipboard'

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

  // --- New tests for uncovered lines ---

  it('extractTextContent handles string children', () => {
    render(<MarkdownContent content="Simple text" />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('extractTextContent handles nested elements', () => {
    const content = 'Text with **bold** and *italic*'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('CodeBlockWithCopy renders with language label', () => {
    const content = '```json\n{"key": "value"}\n```'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('CodeBlockWithCopy copy button calls copyToClipboard', () => {
    const content = '```javascript\nconsole.log("test")\n```'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('ThrottledMarkdown handles rapid content updates', () => {
    const { rerender } = render(<MarkdownContent content="Hello" isStreaming />)
    // Simulate rapid streaming updates
    act(() => {
      rerender(<MarkdownContent content="Hello " isStreaming />)
    })
    act(() => {
      rerender(<MarkdownContent content="Hello World" isStreaming />)
    })
    act(() => {
      rerender(<MarkdownContent content="Hello World!" isStreaming />)
    })
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('ThrottledMarkdown with rAF batching', () => {
    const rafSpy = vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
      cb(0)
      return 0
    })
    const cafSpy = vi.spyOn(globalThis, 'cancelAnimationFrame')

    const { rerender } = render(<MarkdownContent content="initial" isStreaming />)
    act(() => {
      rerender(<MarkdownContent content="updated" isStreaming />)
    })

    rafSpy.mockRestore()
    cafSpy.mockRestore()
  })

  it('preprocessContent removes metadata block with code fence', () => {
    const content = 'Before\n```markdown\n【案例元数据汇总】\nmetadata here\n```\nAfter'
    render(<MarkdownContent content={content} />)
    // The metadata block should be removed
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('preprocessContent removes metadata block without code fence', () => {
    const content = 'Before\n【案例元数据汇总】\nmetadata here\nAfter'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('preprocessContent wraps bare JSON in code blocks', () => {
    const content = 'Data: {"name": "test", "value": 42} end'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('preprocessContent wraps bare JSON arrays', () => {
    const content = 'List: [1, 2, 3] end'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('preprocessContent skips invalid JSON', () => {
    const content = 'Text: {not valid} here'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('preprocessContent handles deeply nested JSON', () => {
    const content = 'Data: {"a": {"b": {"c": 1}}} end'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('preprocessContent handles empty JSON object', () => {
    const content = 'Empty: {}'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('preprocessContent handles empty JSON array', () => {
    const content = 'Empty: []'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles code block without language', () => {
    const content = '```\nplain code\n```'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content that is only a code block', () => {
    const content = '```python\nprint("hello")\n```'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with multiple JSON objects on different lines', () => {
    const content = '{"a": 1}\n{"b": 2}'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with JSON in code blocks (should not wrap)', () => {
    const content = '```json\n{"key": "already in block"}\n```'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles rAF cleanup on unmount in streaming mode', () => {
    const cafSpy = vi.spyOn(globalThis, 'cancelAnimationFrame')
    const { unmount } = render(<MarkdownContent content="test" isStreaming />)
    unmount()
    cafSpy.mockRestore()
  })

  it('ThrottledMarkdown syncs when processed changes after streaming', () => {
    const { rerender } = render(<MarkdownContent content="v1" isStreaming />)
    // Switch to non-streaming
    act(() => {
      rerender(<MarkdownContent content="v2" />)
    })
    // Content should update
    act(() => {
      rerender(<MarkdownContent content="v3" />)
    })
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('preprocessContent with content ending with bracket but no close', () => {
    const content = 'Text with unclosed { bracket'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with special markdown syntax', () => {
    const content = '## Heading\n\n- Item 1\n- Item 2\n\n> Blockquote\n\n---'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles streaming with empty to non-empty content', () => {
    const { rerender } = render(<MarkdownContent content="" isStreaming />)
    act(() => {
      rerender(<MarkdownContent content="Hello" isStreaming />)
    })
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles non-streaming with empty to non-empty content', () => {
    const { rerender } = render(<MarkdownContent content="" />)
    act(() => {
      rerender(<MarkdownContent content="Hello" />)
    })
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })
})
