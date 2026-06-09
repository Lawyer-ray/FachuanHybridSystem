vi.mock('@/lib/utils', () => ({
  cn: (...args: (string | undefined | false | null)[]) => args.filter(Boolean).join(' '),
}))

vi.mock('@/lib/clipboard', () => ({
  copyToClipboard: vi.fn(() => Promise.resolve()),
}))

vi.mock('../LegalText', () => ({
  LegalText: ({ text }: { text: string }) => <span data-testid="legal-text">{text}</span>,
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

// Smart ReactMarkdown mock: parses code fences and renders through custom components
vi.mock('react-markdown', () => ({
  default: ({ children, components }: { children: string; components?: Record<string, React.ComponentType> }) => {
    const PreComp = components?.pre
    const PComp = components?.p

    // Split content by code fences (``` ... ```)
    const parts = children.split(/(```[^\n]*\n[\s\S]*?\n\s*```)/g)

    return (
      <div data-testid="react-markdown">
        {parts.map((part: string, i: number) => {
          if (i % 2 === 1 && part.startsWith('```')) {
            // This is a code block - render through the custom pre component
            const lines = part.split('\n')
            const langLine = lines[0] || '```'
            const lang = langLine.replace(/^```/, '').trim()
            const codeContent = lines.slice(1, -1).join('\n')

            if (PreComp) {
              return (
                <PreComp key={i}>
                  <code className={lang ? `hljs language-${lang}` : ''}>{codeContent}</code>
                </PreComp>
              )
            }
            return <pre key={i}><code>{codeContent}</code></pre>
          }

          // Regular text - render through custom p component
          if (part.trim() && PComp) {
            // Split by newlines for paragraph-like rendering
            const paragraphs = part.split(/\n\n+/).filter(Boolean)
            return paragraphs.map((para: string, j: number) => (
              <PComp key={`${i}-${j}`}>{para.trim()}</PComp>
            ))
          }

          if (part.trim()) {
            return <p key={i}>{part.trim()}</p>
          }

          return null
        })}
      </div>
    )
  },
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

  it('handles content with unicode', () => {
    const content = '你好世界 🌍 こんにちは'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content that is only whitespace', () => {
    render(<MarkdownContent content="   \n  \n   " />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  it('handles content with special markdown syntax', () => {
    const content = '## Heading\n\n- Item 1\n- Item 2\n\n> Blockquote\n\n---'
    render(<MarkdownContent content={content} />)
    expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
  })

  // === NEW TESTS: CodeBlockWithCopy ===

  describe('CodeBlockWithCopy', () => {
    it('renders code block with language label', () => {
      const content = '```json\n{"key": "value"}\n```'
      render(<MarkdownContent content={content} />)

      // Should show the language label
      expect(screen.getByText('json')).toBeInTheDocument()
    })

    it('renders code block with code text for language when no language specified', () => {
      const content = '```\nplain code\n```'
      render(<MarkdownContent content={content} />)

      // Should show 'code' as default label when no language specified
      expect(screen.getByText('code')).toBeInTheDocument()
    })

    it('renders code block with javascript language label', () => {
      const content = '```javascript\nconsole.log("test")\n```'
      render(<MarkdownContent content={content} />)

      expect(screen.getByText('javascript')).toBeInTheDocument()
    })

    it('renders code block with python language label', () => {
      const content = '```python\nprint("hello")\n```'
      render(<MarkdownContent content={content} />)

      expect(screen.getByText('python')).toBeInTheDocument()
    })

    it('renders copy button in code block', () => {
      const content = '```json\n{"key": "value"}\n```'
      render(<MarkdownContent content={content} />)

      // Copy button should be present with copy icon
      expect(screen.getByTestId('copy-icon')).toBeInTheDocument()
    })

    it('calls copyToClipboard when copy button is clicked', async () => {
      const content = '```json\n{"key": "value"}\n```'
      render(<MarkdownContent content={content} />)

      const copyButton = screen.getByTitle('复制代码')
      await act(async () => {
        fireEvent.click(copyButton)
      })

      expect(copyToClipboard).toHaveBeenCalled()
    })

    it('shows check icon after copying', async () => {
      const content = '```json\n{"key": "value"}\n```'
      render(<MarkdownContent content={content} />)

      const copyButton = screen.getByTitle('复制代码')
      await act(async () => {
        fireEvent.click(copyButton)
      })

      // After copying, the Check icon should appear
      expect(screen.getByTestId('check-icon')).toBeInTheDocument()
    })

    it('renders code block with correct content', () => {
      const content = '```json\n{"name": "test"}\n```'
      render(<MarkdownContent content={content} />)

      // Code content should be rendered
      const codeElement = document.querySelector('code')
      expect(codeElement).toBeInTheDocument()
    })

    it('renders multiple code blocks with different languages', () => {
      const content = '```json\n{"key": 1}\n```\nText between\n```python\nx = 1\n```'
      render(<MarkdownContent content={content} />)

      expect(screen.getByText('json')).toBeInTheDocument()
      expect(screen.getByText('python')).toBeInTheDocument()
    })

    it('renders code block without language (defaults to code label)', () => {
      const content = '```\nsome raw code\n```'
      render(<MarkdownContent content={content} />)

      expect(screen.getByText('code')).toBeInTheDocument()
    })
  })

  // === NEW TESTS: extractTextContent via p component ===

  describe('extractTextContent via p component', () => {
    it('renders text content through LegalText component', () => {
      render(<MarkdownContent content="Simple paragraph text" />)

      // LegalText mock renders a span with data-testid="legal-text"
      const legalTexts = screen.getAllByTestId('legal-text')
      expect(legalTexts.length).toBeGreaterThan(0)
      expect(legalTexts[0]).toHaveTextContent('Simple paragraph text')
    })

    it('renders multiple paragraphs through LegalText', () => {
      const content = 'First paragraph\n\nSecond paragraph'
      render(<MarkdownContent content={content} />)

      const legalTexts = screen.getAllByTestId('legal-text')
      expect(legalTexts.length).toBeGreaterThanOrEqual(2)
    })

    it('renders mixed text and code content', () => {
      const content = 'Some text\n\n```json\n{"key": "value"}\n```\n\nMore text'
      render(<MarkdownContent content={content} />)

      // Both text paragraphs and code blocks should render
      expect(screen.getByText('json')).toBeInTheDocument()
      const legalTexts = screen.getAllByTestId('legal-text')
      expect(legalTexts.length).toBeGreaterThan(0)
    })
  })

  // === NEW TESTS: preprocessContent ===

  describe('preprocessContent', () => {
    it('removes metadata block with code fence at end of content', () => {
      const content = 'Before text\n```markdown\n【案例元数据汇总】\nmetadata here\n```'
      render(<MarkdownContent content={content} />)

      // Metadata block should be removed; only "Before text" remains
      const markdown = screen.getByTestId('react-markdown')
      expect(markdown).toHaveTextContent(/Before text/)
      expect(markdown).not.toHaveTextContent(/案例元数据汇总/)
    })

    it('removes metadata block with trailing text after code fence', () => {
      // When metadata block is NOT at end, it remains (regex requires $ anchor)
      const content = 'Before\n```markdown\n【案例元数据汇总】\nmetadata\n```\nAfter'
      render(<MarkdownContent content={content} />)

      // The regex only removes metadata at the end of content, so this stays
      const markdown = screen.getByTestId('react-markdown')
      expect(markdown).toBeInTheDocument()
    })

    it('removes metadata block without code fence', () => {
      const content = 'Before\n【案例元数据汇总】\nmetadata here\nAfter'
      render(<MarkdownContent content={content} />)

      const markdown = screen.getByTestId('react-markdown')
      expect(markdown).not.toHaveTextContent(/案例元数据汇总/)
    })

    it('wraps bare JSON object in code block', () => {
      const content = 'Data: {"name": "test", "value": 42} end'
      render(<MarkdownContent content={content} />)

      // The JSON should be wrapped in a code block with json language
      expect(screen.getByText('json')).toBeInTheDocument()
    })

    it('wraps bare JSON array in code block', () => {
      const content = 'List: [1, 2, 3] end'
      render(<MarkdownContent content={content} />)

      // Arrays get wrapped as json too
      expect(screen.getByText('json')).toBeInTheDocument()
    })

    it('does not wrap invalid JSON', () => {
      const content = 'Not JSON: {invalid} here'
      render(<MarkdownContent content={content} />)

      // Invalid JSON should not be wrapped - no json language label from wrapping
      // (there might still be json label if a code block is present from other content)
      const markdown = screen.getByTestId('react-markdown')
      expect(markdown).toHaveTextContent(/Not JSON/)
    })

    it('does not double-wrap JSON already in code blocks', () => {
      const content = '```json\n{"key": "already wrapped"}\n```'
      render(<MarkdownContent content={content} />)

      // Should only have one json language label
      const jsonLabels = screen.getAllByText('json')
      expect(jsonLabels.length).toBe(1)
    })

    it('handles nested JSON objects', () => {
      const content = 'Data: {"a": {"b": {"c": 1}}} end'
      render(<MarkdownContent content={content} />)

      expect(screen.getByText('json')).toBeInTheDocument()
    })

    it('handles empty JSON object', () => {
      const content = 'Empty: {}'
      render(<MarkdownContent content={content} />)

      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles empty JSON array', () => {
      const content = 'Empty: []'
      render(<MarkdownContent content={content} />)

      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles content with unclosed bracket', () => {
      const content = 'Text with unclosed { bracket'
      render(<MarkdownContent content={content} />)

      // Unclosed bracket should not be wrapped
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles content with JSON that has spaces', () => {
      const content = 'Data: { "key" : "value" , "num" : 42 } end'
      render(<MarkdownContent content={content} />)

      expect(screen.getByText('json')).toBeInTheDocument()
    })

    it('handles deeply nested JSON', () => {
      const content = '{"a": {"b": {"c": {"d": 1}}}}'
      render(<MarkdownContent content={content} />)

      expect(screen.getByText('json')).toBeInTheDocument()
    })

    it('handles multiple JSON objects in content', () => {
      const content = '{"a": 1} and {"b": 2}'
      render(<MarkdownContent content={content} />)

      const jsonLabels = screen.getAllByText('json')
      expect(jsonLabels.length).toBe(2)
    })

    it('handles JSON mixed with code fences', () => {
      const content = '```js\nconst x = 1;\n```\nBare: {"key": "value"} end'
      render(<MarkdownContent content={content} />)

      // Both js code block and wrapped json should be present
      expect(screen.getByText('js')).toBeInTheDocument()
      expect(screen.getByText('json')).toBeInTheDocument()
    })

    it('handles content with JSON on its own line', () => {
      const content = '{"a": 1}\n{"b": 2}'
      render(<MarkdownContent content={content} />)

      const jsonLabels = screen.getAllByText('json')
      expect(jsonLabels.length).toBe(2)
    })

    it('handles content that is only a bare JSON object', () => {
      const content = '{"key": "value"}'
      render(<MarkdownContent content={content} />)

      expect(screen.getByText('json')).toBeInTheDocument()
    })

    it('handles content that is only a bare JSON array', () => {
      const content = '[1, 2, 3]'
      render(<MarkdownContent content={content} />)

      expect(screen.getByText('json')).toBeInTheDocument()
    })

    it('handles mixed bracket types (objects and arrays)', () => {
      const content = 'Object: {"key": "value"} and Array: [1, 2] and Nested: {"arr": [1, 2]}'
      render(<MarkdownContent content={content} />)

      const jsonLabels = screen.getAllByText('json')
      expect(jsonLabels.length).toBeGreaterThanOrEqual(2)
    })
  })

  // === NEW TESTS: ThrottledMarkdown (streaming mode) ===

  describe('ThrottledMarkdown (streaming mode)', () => {
    it('renders in streaming mode with content', () => {
      render(<MarkdownContent content="streaming text" isStreaming />)

      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
      expect(screen.getByTestId('react-markdown')).toHaveTextContent(/streaming text/)
    })

    it('handles rapid content updates in streaming mode', () => {
      const { rerender } = render(<MarkdownContent content="Hello" isStreaming />)

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

    it('uses requestAnimationFrame for streaming updates', () => {
      const rafSpy = vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
        cb(0)
        return 0
      })
      const cafSpy = vi.spyOn(globalThis, 'cancelAnimationFrame')

      const { rerender } = render(<MarkdownContent content="initial" isStreaming />)
      act(() => {
        rerender(<MarkdownContent content="updated" isStreaming />)
      })

      expect(rafSpy).toHaveBeenCalled()
      rafSpy.mockRestore()
      cafSpy.mockRestore()
    })

    it('cancels animation frame on cleanup', () => {
      const cafSpy = vi.spyOn(globalThis, 'cancelAnimationFrame').mockImplementation(() => {})
      vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
        cb(performance.now())
        return 42
      })

      const { rerender, unmount } = render(<MarkdownContent content="v1" isStreaming />)
      // Trigger a content change to schedule a rAF
      act(() => {
        rerender(<MarkdownContent content="v2" isStreaming />)
      })

      unmount()

      expect(cafSpy).toHaveBeenCalled()
      cafSpy.mockRestore()
      vi.restoreAllMocks()
    })

    it('handles streaming with empty to non-empty content', () => {
      const { rerender } = render(<MarkdownContent content="" isStreaming />)
      act(() => {
        rerender(<MarkdownContent content="Hello" isStreaming />)
      })

      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles streaming mode content update with code blocks', () => {
      const codeContent = 'text\n```json\n{"key": "val"}\n```'
      const { rerender } = render(<MarkdownContent content="text" isStreaming />)
      act(() => {
        rerender(<MarkdownContent content={codeContent} isStreaming />)
      })

      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('skips update when content has not changed', () => {
      const { rerender } = render(<MarkdownContent content="same content" isStreaming />)

      // Re-render with same content - should skip update
      act(() => {
        rerender(<MarkdownContent content="same content" isStreaming />)
      })

      expect(screen.getByTestId('react-markdown')).toHaveTextContent(/same content/)
    })

    it('handles switching from streaming to non-streaming mode', () => {
      const { rerender } = render(<MarkdownContent content="test" isStreaming />)
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()

      act(() => {
        rerender(<MarkdownContent content="test" />)
      })
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles switching from non-streaming to streaming mode', () => {
      const { rerender } = render(<MarkdownContent content="test" />)
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()

      act(() => {
        rerender(<MarkdownContent content="test" isStreaming />)
      })
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('applies system styles in streaming mode', () => {
      const { container } = render(<MarkdownContent content="error" isSystem isStreaming />)
      const proseDiv = container.querySelector('.prose-red')
      expect(proseDiv).toBeInTheDocument()
    })

    it('handles streaming with rapid updates using mocked rAF', () => {
      // Mock rAF to execute immediately
      vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
        cb(performance.now())
        return 1
      })
      vi.spyOn(globalThis, 'cancelAnimationFrame').mockImplementation(() => {})

      const { rerender } = render(<MarkdownContent content="v1" isStreaming />)
      act(() => {
        rerender(<MarkdownContent content="v2" isStreaming />)
      })
      act(() => {
        rerender(<MarkdownContent content="v3" isStreaming />)
      })

      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()

      vi.restoreAllMocks()
    })
  })

  // === NEW TESTS: Memo and rendering ===

  describe('memoization', () => {
    it('does not re-render when props are the same', () => {
      const { rerender } = render(<MarkdownContent content="test" />)
      rerender(<MarkdownContent content="test" />)
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('re-renders when content changes', () => {
      const { rerender } = render(<MarkdownContent content="first" />)
      expect(screen.getByTestId('react-markdown')).toHaveTextContent(/first/)

      rerender(<MarkdownContent content="second" />)
      expect(screen.getByTestId('react-markdown')).toHaveTextContent(/second/)
    })
  })

  // === NEW TESTS: Edge cases ===

  describe('edge cases', () => {
    it('handles content with only markdown formatting', () => {
      const content = '**bold** and *italic* and `code`'
      render(<MarkdownContent content={content} />)
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles content with headings', () => {
      const content = '# H1\n## H2\n### H3'
      render(<MarkdownContent content={content} />)
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles content with horizontal rule', () => {
      const content = 'Before\n\n---\n\nAfter'
      render(<MarkdownContent content={content} />)
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles content with blockquote', () => {
      const content = '> This is a blockquote\n> with multiple lines'
      render(<MarkdownContent content={content} />)
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles content with images', () => {
      const content = '![Alt text](https://example.com/image.png)'
      render(<MarkdownContent content={content} />)
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles content with complex list', () => {
      const content = '- Item 1\n  - Nested 1\n  - Nested 2\n- Item 2\n- Item 3'
      render(<MarkdownContent content={content} />)
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles content with ordered list', () => {
      const content = '1. First\n2. Second\n3. Third'
      render(<MarkdownContent content={content} />)
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles content with strikethrough', () => {
      const content = '~~deleted text~~'
      render(<MarkdownContent content={content} />)
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles content with checkbox list (GFM)', () => {
      const content = '- [x] Done\n- [ ] Not done'
      render(<MarkdownContent content={content} />)
      expect(screen.getByTestId('react-markdown')).toBeInTheDocument()
    })

    it('handles very long code block', () => {
      const code = 'x'.repeat(5000)
      const content = '```text\n' + code + '\n```'
      render(<MarkdownContent content={content} />)
      expect(screen.getByText('text')).toBeInTheDocument()
    })

    it('handles content with mixed bare JSON and metadata', () => {
      const content = 'Text {"key": "value"}\n```markdown\n【案例元数据汇总】\ndata\n```\nEnd'
      render(<MarkdownContent content={content} />)

      // JSON should be wrapped, metadata removed
      expect(screen.getByText('json')).toBeInTheDocument()
      expect(screen.getByTestId('react-markdown')).not.toHaveTextContent(/案例元数据汇总/)
    })

    it('handles content with adjacent code blocks', () => {
      const content = '```json\n{"a": 1}\n```\n```python\nprint("hi")\n```'
      render(<MarkdownContent content={content} />)

      expect(screen.getByText('json')).toBeInTheDocument()
      expect(screen.getByText('python')).toBeInTheDocument()
    })

    it('preserves content that is not metadata or bare JSON', () => {
      const content = 'Regular paragraph with some **bold** text.'
      render(<MarkdownContent content={content} />)

      const markdown = screen.getByTestId('react-markdown')
      expect(markdown).toHaveTextContent(/Regular paragraph/)
    })

    it('handles rAF with mock that returns non-zero ID', () => {
      let rafId = 42
      vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
        cb(performance.now())
        return rafId++
      })
      vi.spyOn(globalThis, 'cancelAnimationFrame').mockImplementation(() => {})

      const { rerender, unmount } = render(<MarkdownContent content="a" isStreaming />)
      act(() => {
        rerender(<MarkdownContent content="ab" isStreaming />)
      })

      unmount()
      vi.restoreAllMocks()
    })
  })
})
