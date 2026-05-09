/** 批量分析结果格式化工具 */

export interface BatchResultData {
  case_number: string
  cause: string
  court: string
  judge: string
  clerk: string
  is_relevant: boolean
  conclusion: string
  analysis: string
}

/**
 * 解析批量分析 JSON 结果，返回结构化数据。
 * 如果内容不是合法 JSON 或缺少关键字段，返回 null。
 */
export function parseBatchResult(content: string): BatchResultData | null {
  const trimmed = content.trim()
  if (!trimmed.startsWith('{')) return null

  try {
    const obj = JSON.parse(trimmed)
    // 必须有 analysis 字段才算有效的批量分析结果
    if (typeof obj.analysis !== 'string') return null
    return {
      case_number: obj.case_number ?? '未注明',
      cause: obj.cause ?? '未注明',
      court: obj.court ?? '未注明',
      judge: obj.judge ?? '未注明',
      clerk: obj.clerk ?? '未注明',
      is_relevant: obj.is_relevant !== false,
      conclusion: obj.conclusion ?? '',
      analysis: obj.analysis,
    }
  } catch {
    return null
  }
}

/**
 * 将 JSON 结果格式化为可读 Markdown（写入 DB 用）。
 * 非 JSON 内容原样返回。
 */
export function formatBatchContent(content: string): string {
  const parsed = parseBatchResult(content)
  if (!parsed) return content

  const parts: string[] = []

  // 元数据行
  const metaItems = [
    parsed.case_number !== '未注明' && `**案号**：${parsed.case_number}`,
    parsed.cause !== '未注明' && `**案由**：${parsed.cause}`,
    parsed.court !== '未注明' && `**审理法院**：${parsed.court}`,
    parsed.judge !== '未注明' && `**法官**：${parsed.judge}`,
    parsed.clerk !== '未注明' && `**书记员**：${parsed.clerk}`,
  ].filter(Boolean)

  if (metaItems.length > 0) {
    parts.push(metaItems.join(' | '))
    parts.push('')
  }

  // 相关性标签
  parts.push(parsed.is_relevant ? '**与研究问题相关**' : '**与研究问题无关**')
  parts.push('')

  // 结论
  if (parsed.conclusion) {
    parts.push(`> ${parsed.conclusion}`)
    parts.push('')
  }

  // 分析正文
  if (parsed.analysis) {
    parts.push(parsed.analysis)
  }

  return parts.join('\n')
}
