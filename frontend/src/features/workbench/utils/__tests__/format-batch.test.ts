/**
 * Batch Format Utils Tests
 * 测试批量分析结果解析和格式化工具
 */

import { parseBatchResult, formatBatchContent } from '../format-batch'

describe('parseBatchResult', () => {
  const validJson = JSON.stringify({
    case_number: '(2024)京0101民初12345号',
    cause: '合同纠纷',
    court: '北京市第一中级人民法院',
    judge: '张三',
    clerk: '李四',
    is_relevant: true,
    conclusion: '本案与研究问题相关',
    analysis: '详细分析内容...',
  })

  it('parses valid JSON string', () => {
    const result = parseBatchResult(validJson)
    expect(result).not.toBeNull()
    expect(result?.case_number).toBe('(2024)京0101民初12345号')
    expect(result?.cause).toBe('合同纠纷')
    expect(result?.analysis).toBe('详细分析内容...')
  })

  it('parses JSON wrapped in code fence', () => {
    const wrapped = '```json\n' + validJson + '\n```'
    const result = parseBatchResult(wrapped)
    expect(result).not.toBeNull()
    expect(result?.case_number).toBe('(2024)京0101民初12345号')
  })

  it('parses JSON wrapped in plain code fence (no language)', () => {
    const wrapped = '```\n' + validJson + '\n```'
    const result = parseBatchResult(wrapped)
    expect(result).not.toBeNull()
  })

  it('returns null for non-JSON content', () => {
    expect(parseBatchResult('This is not JSON')).toBeNull()
  })

  it('returns null for JSON without analysis field', () => {
    const noAnalysis = JSON.stringify({ case_number: 'test' })
    expect(parseBatchResult(noAnalysis)).toBeNull()
  })

  it('returns null for empty string', () => {
    expect(parseBatchResult('')).toBeNull()
  })

  it('fills missing optional fields with defaults', () => {
    const minimal = JSON.stringify({ analysis: 'test analysis' })
    const result = parseBatchResult(minimal)
    expect(result).not.toBeNull()
    expect(result?.case_number).toBe('未注明')
    expect(result?.cause).toBe('未注明')
    expect(result?.court).toBe('未注明')
    expect(result?.is_relevant).toBe(true)
  })

  it('handles is_relevant=false correctly', () => {
    const json = JSON.stringify({ analysis: 'test', is_relevant: false })
    const result = parseBatchResult(json)
    expect(result?.is_relevant).toBe(false)
  })

  it('handles JSON with extra text before and after', () => {
    const extraText = 'Here is the result:\n' + validJson + '\nDone.'
    const result = parseBatchResult(extraText)
    expect(result).not.toBeNull()
    expect(result?.analysis).toBe('详细分析内容...')
  })

  it('handles JSON with trailing comma (LLM common issue)', () => {
    const withTrailing = '{"analysis": "test", "cause": "合同纠纷",}'
    const result = parseBatchResult(withTrailing)
    expect(result).not.toBeNull()
    expect(result?.cause).toBe('合同纠纷')
  })

  it('handles JSON with invalid escape sequences (LLM artifact)', () => {
    // Simulate LLM output with \\' which is invalid JSON
    const withBadEscape = '{"analysis": "test", "cause": "纠纷"}'
    const result = parseBatchResult(withBadEscape)
    expect(result).not.toBeNull()
    expect(result?.cause).toBe('纠纷')
  })
})

describe('formatBatchContent', () => {
  const validContent = JSON.stringify({
    case_number: '(2024)京0101民初12345号',
    cause: '合同纠纷',
    court: '北京市第一中级人民法院',
    judge: '张三',
    clerk: '李四',
    is_relevant: true,
    conclusion: '支持原告诉讼请求',
    analysis: '法院认为，原告主张成立...',
  })

  it('formats valid JSON into readable markdown', () => {
    const result = formatBatchContent(validContent)
    expect(result).toContain('**案号**')
    expect(result).toContain('(2024)京0101民初12345号')
    expect(result).toContain('**案由**')
    expect(result).toContain('**与研究问题相关**')
    expect(result).toContain('支持原告诉讼请求')
    expect(result).toContain('法院认为')
  })

  it('returns original content for non-JSON', () => {
    const plain = 'This is plain text content'
    expect(formatBatchContent(plain)).toBe(plain)
  })

  it('marks irrelevant results correctly', () => {
    const irrelevant = JSON.stringify({ analysis: 'test', is_relevant: false })
    const result = formatBatchContent(irrelevant)
    expect(result).toContain('**与研究问题无关**')
  })

  it('omits metadata line when all values are default', () => {
    const minimal = JSON.stringify({ analysis: 'analysis only' })
    const result = formatBatchContent(minimal)
    expect(result).toContain('analysis only')
    expect(result).not.toContain('**案号**')
  })

  it('includes conclusion in blockquote when present', () => {
    const withConclusion = JSON.stringify({ analysis: 'test', conclusion: 'Important conclusion' })
    const result = formatBatchContent(withConclusion)
    expect(result).toContain('> Important conclusion')
  })

  it('omits conclusion blockquote when empty', () => {
    const noConclusion = JSON.stringify({ analysis: 'test', conclusion: '' })
    const result = formatBatchContent(noConclusion)
    expect(result).not.toContain('> \n')
  })

  it('handles wrapped code fence content', () => {
    const wrapped = '```json\n' + validContent + '\n```'
    const result = formatBatchContent(wrapped)
    expect(result).toContain('**案号**')
  })
})
