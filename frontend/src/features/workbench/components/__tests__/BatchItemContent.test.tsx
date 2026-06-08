/**
 * BatchItemContent Component Tests
 * 测试批量分析结果卡片组件
 */

vi.mock('../MarkdownContent', () => ({
  MarkdownContent: ({ content }: { content: string }) => <div data-testid="markdown">{content}</div>,
}))

import { render, screen } from '@testing-library/react'
import { BatchItemContent } from '../BatchItemContent'

describe('BatchItemContent', () => {
  it('renders markdown content for non-JSON input', () => {
    render(<BatchItemContent content="Plain text content" />)
    expect(screen.getByTestId('markdown')).toHaveTextContent('Plain text content')
  })

  it('renders structured result for valid JSON analysis', () => {
    const content = '### doc.pdf\n\n' + JSON.stringify({
      case_number: '(2024)京0101民初12345号',
      cause: '合同纠纷',
      court: '北京市第一中级人民法院',
      judge: '张三',
      clerk: '李四',
      is_relevant: true,
      conclusion: '支持原告诉讼请求',
      analysis: '法院认为...',
    })
    render(<BatchItemContent content={content} />)
    expect(screen.getByText('doc.pdf')).toBeInTheDocument()
    expect(screen.getByText('相关')).toBeInTheDocument()
    expect(screen.getByText('支持原告诉讼请求')).toBeInTheDocument()
    expect(screen.getByTestId('markdown')).toHaveTextContent('法院认为...')
  })

  it('shows irrelevance badge when is_relevant is false', () => {
    const content = JSON.stringify({
      analysis: '分析内容',
      is_relevant: false,
    })
    render(<BatchItemContent content={content} />)
    expect(screen.getByText('无关')).toBeInTheDocument()
  })

  it('renders file name when content starts with ### heading and has parseable JSON body', () => {
    const jsonBody = JSON.stringify({ analysis: '正文分析', is_relevant: true })
    const content = `### test-doc.pdf\n\n${jsonBody}`
    render(<BatchItemContent content={content} />)
    expect(screen.getByText('test-doc.pdf')).toBeInTheDocument()
  })

  it('renders conclusion block when present', () => {
    const content = JSON.stringify({
      analysis: '正文分析',
      conclusion: '重要结论',
    })
    render(<BatchItemContent content={content} />)
    expect(screen.getByText('重要结论')).toBeInTheDocument()
    expect(screen.getByText('结论')).toBeInTheDocument()
  })

  it('does not render conclusion block when empty', () => {
    const content = JSON.stringify({
      analysis: '正文',
      conclusion: '',
    })
    render(<BatchItemContent content={content} />)
    expect(screen.queryByText('结论')).not.toBeInTheDocument()
  })

  it('renders metadata fields with known values', () => {
    const content = JSON.stringify({
      case_number: '(2024)京0101民初12345号',
      cause: '合同纠纷',
      analysis: '正文',
    })
    render(<BatchItemContent content={content} />)
    expect(screen.getByText('案号')).toBeInTheDocument()
    expect(screen.getByText('案由')).toBeInTheDocument()
  })

  it('falls back to markdown for non-JSON content', () => {
    render(<BatchItemContent content="Not JSON at all" />)
    expect(screen.getByTestId('markdown')).toHaveTextContent('Not JSON at all')
  })
})
