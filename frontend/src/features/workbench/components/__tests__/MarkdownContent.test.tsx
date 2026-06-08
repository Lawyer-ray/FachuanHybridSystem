/**
 * MarkdownContent Component Tests
 * 测试 Markdown 内容渲染组件
 */

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
  default: ({ children }: { children: string }) => <div data-testid="react-markdown">{children}</div>,
}))

vi.mock('remark-gfm', () => ({ default: () => {} }))
vi.mock('rehype-highlight', () => ({ default: () => {} }))

import { render, screen } from '@testing-library/react'
import { MarkdownContent } from '../MarkdownContent'

describe('MarkdownContent', () => {
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
})
