/**
 * 转录映射：user 消息里各类「锚点块 / 引用块」的出站构建与回放解析。
 *
 * **出站构造与回放解析必须成对放在本文件**——`build*` 与 `split*` 是互逆的
 * 一对（正则与构建侧的引号/换行归一严格对应）。分开放到两个文件里，改一边
 * 忘另一边的漂移无法在 review 时看见，症状是「历史回看时引用变成一坨长文本」
 * 或「归属 id 被切进标题」。
 */

import type { AgentHistoryMessage, BizHint, ChatMessage, SentRefMeta, SelectionQuote } from '../types'

/**
 * 引用块行（发送时由 outgoing 拼入消息）：
 * - 文件（落了附件）：`[已引用文件：name (attachment_id=…, contract_id=N, subpath="…")]`
 *   案件文件把 contract_id 换成 case_id
 * - 目录（不落附件）：`[已引用目录：name (contract_id=N, subpath="…")]`
 *   模型收到后先用 list_folder_files 列目录、再 read_folder_file 读文件
 */
const SENT_REF_RE =
  /^\[已引用(文件|目录)：(.+?) \((?:attachment_id=[0-9a-f-]+, )?(contract_id|case_id)=(\d+), subpath="(.+?)"\)\]$/

/**
 * 把 user 消息正文拆成「引用块 + 剩余正文」。
 * 历史回放与本地发送走同一解析，气泡上方把引用重放为 chip——否则回看
 * 会话时引用只是一坨长文本。非引用消息原样返回（body 不动）。
 */
export function splitRefBlocks(content: string): { refs: SentRefMeta[]; body: string } {
  const refs: SentRefMeta[] = []
  const kept: string[] = []
  for (const line of content.split('\n')) {
    const m = SENT_REF_RE.exec(line.trim())
    if (m?.[1] && m[2] && m[3] && m[4] && m[5]) {
      refs.push({
        isFolder: m[1] === '目录' || undefined,
        name: m[2],
        kind: m[3] === 'case_id' ? 'case' : 'contract',
        ownerId: Number(m[4]),
        subpath: m[5],
      })
    } else kept.push(line)
  }
  if (refs.length === 0) return { refs, body: content }
  // 去掉引用块后正文可能只剩空白（默认语被引用块替换的场景）——保留原始
  // 换行结构，仅去掉首尾空段
  return { refs, body: kept.join('\n').replace(/^\n+|\n+$/g, '') }
}

/** 「[当前页面：xxx]」行——通用模式下 send 注入的页面锚点，回放折叠为 chip */
const PAGE_HINT_RE = /^\[当前页面：(.+?)\]$/

/**
 * 「[当前业务：本委托「xx」 contract_id=N]」行——业务范围（详情页工作区/浮层
 * context）下 send 注入的归属锚点，模型据此直达对应绑定文件夹与数据。
 *
 * 与 buildBizHintBlock 严格互逆：标题里的引号在构建时归一成「“”」，
 * 保证闭引号唯一（否则标题自带 `」` 时非贪婪匹配会切在错的位置，
 * 尾部的 contract_id 就成了标题的一部分）。
 */
const BIZ_HINT_RE = /^\[当前业务：(本委托|本案)“(.+?)” (contract_id|case_id)=(\d+)\]$/

/**
 * 框选引用块（豆包式引用的出站形态）：
 * `[已引用选段："…" (contract_id=N, subpath="…")]`
 *
 * 引号里的文本在构建时把 `"` 全量替换成 `”`（见 buildSelectionQuoteBlock），
 * 保证闭引号唯一、正则可以无歧义地非贪婪匹配回来。
 */
const SENT_QUOTE_RE = /^\[已引用选段："(.+?)" \((contract_id|case_id)=(\d+), subpath="(.+?)"\)\]$/

/** 把 user 消息里的框选引用块拆出来（历史回放与本地发送同一解析） */
export function splitQuoteBlock(content: string): { quote: SelectionQuote | null; body: string } {
  const kept: string[] = []
  let quote: SelectionQuote | null = null
  for (const line of content.split('\n')) {
    const m = SENT_QUOTE_RE.exec(line.trim())
    if (m?.[1] && m[2] && m[3] && m[4] && !quote) {
      quote = {
        text: m[1],
        kind: m[2] === 'case_id' ? 'case' : 'contract',
        ownerId: Number(m[3]),
        subpath: m[4],
        name: m[4].split('/').pop() || m[4],
      }
    } else kept.push(line)
  }
  if (!quote) return { quote: null, body: content }
  return { quote, body: kept.join('\n').replace(/^\n+|\n+$/g, '') }
}

/** 把 user 消息开头的页面锚点行拆出来；无锚点原样返回 */
export function splitPageHintLine(content: string): { pageHint: string | null; body: string } {
  const lines = content.split('\n')
  const first = lines[0]?.trim() ?? ''
  const m = PAGE_HINT_RE.exec(first)
  if (!m?.[1]) return { pageHint: null, body: content }
  return { pageHint: m[1], body: lines.slice(1).join('\n').replace(/^\n+/, '') }
}

/**
 * 归属锚点的规范化（构建与解析共用，保证互逆）：标尺只保留落库的 `kind`，
 * 单位词与 id 键名都由它派生，不额外存一份可漂移的副本。
 */
export function bizHintFromContext(context: { origin: 'case' | 'contract'; refId: number; title: string }): BizHint {
  return { kind: context.origin, title: context.title.trim(), refId: context.refId }
}

/** 标题进锚点前的整形：换行归一成空格（锚点必须单行），引号归一成「“”」
 *
 * 为什么要归引号：锚点靠 `“…”` 定界标题，标题自带 `「`/`」`（如
 * `「示例甲方」专项案`）时 `(.+?)` 会在第一个 `」` 停住，剩下的 `…」 contract_id=393`
 * 全被当成标题，唯一的机器可读归属 id 就丢了。归一后闭引号唯一，
 * 游标（向模型发的原文）里的标题也只是显示用，换这对弯引号零损失。
 */
export function normalizeBizHintTitle(raw: string): string {
  return raw.replace(/\s*\n\s*/g, ' ').trim().replace(/「/g, '“').replace(/」/g, '”')
}

/** 构建业务归属锚点行（发送侧；与 BIZ_HINT_RE 严格互逆） */
export function buildBizHintBlock(context: { origin: 'case' | 'contract'; refId: number; title: string }, text: string): string {
  const hint = bizHintFromContext(context)
  const unit = hint.kind === 'case' ? '本案' : '本委托'
  const idKey = hint.kind === 'case' ? 'case_id' : 'contract_id'
  return `[当前业务：${unit}“${normalizeBizHintTitle(hint.title)}” ${idKey}=${hint.refId}]\n${text}`
}

/** 把 user 消息开头的业务锚点行拆出来（与页面锚点同构）；无锚点原样返回 */
export function splitBizHintLine(content: string): { bizHint: BizHint | null; body: string } {
  const lines = content.split('\n')
  const first = lines[0]?.trim() ?? ''
  const m = BIZ_HINT_RE.exec(first)
  if (!m?.[1] || !m[2] || !m[3] || !m[4]) return { bizHint: null, body: content }
  return {
    bizHint: { kind: m[3] === 'case_id' ? 'case' : 'contract', title: m[2], refId: Number(m[4]) },
    body: lines.slice(1).join('\n').replace(/^\n+/, ''),
  }
}

/** 归属锚点的展示三段：单位 · 名称 · #id（id 单独成段，不再被整串截断吃掉） */
export function bizHintParts(hint: BizHint): { unit: string; title: string; ref: string } {
  return { unit: hint.kind === 'case' ? '本案' : '本委托', title: hint.title, ref: `#${hint.refId}` }
}

/**
 * 历史消息 → 转录气泡。
 * tool 消息后端截断到 8000 字符，前端预览再收一刀；truncated 标记透传。
 *
 * user 行按注入顺序逐层剥离锚点/引用块（页面锚点 → 业务锚点 → 引用块 →
 * 框选块），每层都把上一层的正文继续往下传——与出站拼接顺序严格对应。
 */
export function historyToMessages(rows: AgentHistoryMessage[]): ChatMessage[] {
  return rows.map((row) => {
    const hintSplit = row.role === 'user' ? splitPageHintLine(row.content) : null
    const bizSplit = row.role === 'user' ? splitBizHintLine(hintSplit?.body ?? row.content) : null
    const refsSplit = row.role === 'user' ? splitRefBlocks(bizSplit?.body ?? row.content) : null
    const quoteSplit = row.role === 'user' ? splitQuoteBlock(refsSplit?.body ?? row.content) : null
    return {
      id: `db-${row.message_id}`,
      role: row.role,
      content: row.role === 'tool' ? row.content.slice(0, 2000) : (quoteSplit?.body ?? row.content),
      pageHint: hintSplit?.pageHint ?? undefined,
      bizHint: bizSplit?.bizHint ?? undefined,
      refs: refsSplit?.refs.length ? refsSplit.refs : undefined,
      quote: quoteSplit?.quote ?? undefined,
      toolName: row.tool_name || undefined,
      truncated: row.metadata?.truncated === true || undefined,
    }
  })
}
