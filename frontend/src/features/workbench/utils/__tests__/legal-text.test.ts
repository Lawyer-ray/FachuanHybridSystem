/**
 * Legal Text Utils Tests
 * 测试法律文本处理工具（案号、法条引用、金额识别）
 */

import { findLegalReferences, getCaseNumberInfo, getLawArticleInfo, formatMoneyDisplay } from '../legal-text'

describe('findLegalReferences', () => {
  it('returns empty array for plain text without legal references', () => {
    const result = findLegalReferences('This is plain text')
    expect(result).toEqual([])
  })

  it('detects case numbers in Chinese format', () => {
    const text = '依据（2024）京0101民初12345号判决书'
    const result = findLegalReferences(text)
    expect(result.length).toBeGreaterThanOrEqual(1)
    const caseNum = result.find((m) => m.type === 'case_number')
    expect(caseNum).toBeDefined()
    expect(caseNum?.text).toContain('2024')
  })

  it('detects law article references', () => {
    const text = '根据《中华人民共和国民法典》第一百二十三条第一款的规定'
    const result = findLegalReferences(text)
    expect(result.length).toBeGreaterThanOrEqual(1)
    const lawRef = result.find((m) => m.type === 'law_article')
    expect(lawRef).toBeDefined()
    expect(lawRef?.text).toContain('民法典')
  })

  it('detects money references', () => {
    const text = '赔偿人民币100,000元'
    const result = findLegalReferences(text)
    const money = result.find((m) => m.type === 'money')
    expect(money).toBeDefined()
    expect(money?.text).toContain('100,000')
  })

  it('detects money with RMB prefix', () => {
    const text = '支付RMB50000元'
    const result = findLegalReferences(text)
    const money = result.find((m) => m.type === 'money')
    expect(money).toBeDefined()
  })

  it('returns results sorted by position', () => {
    const text = '依据（2024）京0101民初1号判决，赔偿人民币10000元，根据《民法典》第一条'
    const result = findLegalReferences(text)
    for (let i = 1; i < result.length; i++) {
      expect(result[i].index).toBeGreaterThanOrEqual(result[i - 1].index)
    }
  })

  it('returns empty array for empty string', () => {
    expect(findLegalReferences('')).toEqual([])
  })
})

describe('getCaseNumberInfo', () => {
  it('parses full-width parentheses case number', () => {
    const result = getCaseNumberInfo('（2024）京0101民初12345号')
    expect(result.year).toBe('2024')
    expect(result.number).toContain('号')
    expect(result.label).toBe('（2024）京0101民初12345号')
  })

  it('parses half-width parentheses case number', () => {
    const result = getCaseNumberInfo('(2023)沪0115民初67890号')
    expect(result.year).toBe('2023')
    expect(result.number).toContain('号')
  })

  it('returns empty year for invalid format', () => {
    const result = getCaseNumberInfo('no-case-number')
    expect(result.year).toBe('')
  })

  it('returns original label unchanged', () => {
    const input = '（2024）京0101民初12345号'
    const result = getCaseNumberInfo(input)
    expect(result.label).toBe(input)
  })
})

describe('getLawArticleInfo', () => {
  it('extracts law name and article from reference', () => {
    const result = getLawArticleInfo('《中华人民共和国民法典》第一百二十三条')
    expect(result.lawName).toBe('中华人民共和国民法典')
    expect(result.article).toContain('一百二十三条')
  })

  it('extracts law name with short name', () => {
    const result = getLawArticleInfo('《民法典》第一条')
    expect(result.lawName).toBe('民法典')
  })

  it('returns empty lawName for text without book title marks', () => {
    const result = getLawArticleInfo('no reference')
    expect(result.lawName).toBe('')
  })

  it('returns original text as article when no match', () => {
    const result = getLawArticleInfo('random text')
    expect(result.article).toBe('random text')
  })
})

describe('formatMoneyDisplay', () => {
  it('returns input text unchanged', () => {
    expect(formatMoneyDisplay('人民币100,000元')).toBe('人民币100,000元')
  })

  it('handles empty string', () => {
    expect(formatMoneyDisplay('')).toBe('')
  })
})
