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
  let trimmed = content.trim()

  // 剥离 ```json ... ``` 代码围栏
  const fenceMatch = trimmed.match(/```(?:json)?\s*\n?([\s\S]*?)\n?\s*```/)
  if (fenceMatch) trimmed = fenceMatch[1].trim()

  // 尝试找到 JSON 对象的起止位置
  const jsonStart = trimmed.indexOf('{')
  if (jsonStart === -1) return null

  // 从第一个 { 开始，找到匹配的 }
  let depth = 0
  let jsonEnd = -1
  for (let i = jsonStart; i < trimmed.length; i++) {
    if (trimmed[i] === '{') depth++
    else if (trimmed[i] === '}') {
      depth--
      if (depth === 0) {
        jsonEnd = i + 1
        break
      }
    }
  }

  if (jsonEnd === -1) return null
  const jsonStr = trimmed.slice(jsonStart, jsonEnd)

  try {
    const obj = JSON.parse(jsonStr)
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
