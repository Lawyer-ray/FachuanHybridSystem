/** 法律文本处理工具函数 — 案号、法条引用、金额识别 */

/** 案号正则 — 匹配 (年份)法院代字案件类型+编号 格式 */
const CASE_NUMBER_RE =
  /[(（]\d{4}[)）][一-鿿]{1,8}\d{1,4}(?:民|刑|行|执|破|知|仲)\S{0,6}\d{1,6}号/g

/** 法条引用正则 — 匹配《法律名称》第X条 */
const LAW_ARTICLE_RE =
  /《[^》]{2,30}》第[一二三四五六七八九十百千\d]+条(?:第[一二三四五六七八九十\d]+款)?/g

/** 金额正则 — 匹配人民币XXX元 / ¥XXX / X万元 */
const MONEY_RE =
  /(?:人民币|RMB|￥|¥)\s*[\d,]+(?:\.\d+)?(?:\s*(?:万|亿))?元?|[\d,]+(?:\.\d+)?(?:\s*(?:万|亿))\s*元/g

export interface LegalMatch {
  type: 'case_number' | 'law_article' | 'money'
  text: string
  index: number
  length: number
}

/** 从文本中提取所有法律引用 */
export function findLegalReferences(text: string): LegalMatch[] {
  const matches: LegalMatch[] = []

  for (const match of text.matchAll(CASE_NUMBER_RE)) {
    matches.push({
      type: 'case_number',
      text: match[0],
      index: match.index!,
      length: match[0].length,
    })
  }

  for (const match of text.matchAll(LAW_ARTICLE_RE)) {
    matches.push({
      type: 'law_article',
      text: match[0],
      index: match.index!,
      length: match[0].length,
    })
  }

  for (const match of text.matchAll(MONEY_RE)) {
    matches.push({
      type: 'money',
      text: match[0],
      index: match.index!,
      length: match[0].length,
    })
  }

  // 按位置排序，处理重叠
  matches.sort((a, b) => a.index - b.index)
  return deduplicateOverlapping(matches)
}

/** 去除重叠匹配，保留更长的 */
function deduplicateOverlapping(matches: LegalMatch[]): LegalMatch[] {
  const result: LegalMatch[] = []
  let lastEnd = -1

  for (const m of matches) {
    if (m.index >= lastEnd) {
      result.push(m)
      lastEnd = m.index + m.length
    }
  }

  return result
}

/** 案号详情弹窗数据 */
export function getCaseNumberInfo(caseNumber: string): { label: string; year: string; court: string; number: string } {
  const cleaned = caseNumber.replace(/[（]/g, '(').replace(/[）]/g, ')')
  const yearMatch = cleaned.match(/\((\d{4})\)/)
  const year = yearMatch ? yearMatch[1] : ''
  const afterYear = cleaned.replace(/\(\d{4}\)/, '')
  const numberMatch = afterYear.match(/(\S+?)(\d+号)$/)
  const court = numberMatch ? numberMatch[1] : ''
  const number = numberMatch ? numberMatch[2] : ''

  return { label: caseNumber, year, court, number }
}

/** 法条信息 */
export function getLawArticleInfo(text: string): { lawName: string; article: string } {
  const nameMatch = text.match(/《([^》]+)》/)
  const articleMatch = text.match(/第([\d一二三四五六七八九十百千]+条.*)/)
  return {
    lawName: nameMatch ? nameMatch[1] : '',
    article: articleMatch ? articleMatch[1] : text,
  }
}

/** 格式化金额显示 */
export function formatMoneyDisplay(text: string): string {
  return text
}
