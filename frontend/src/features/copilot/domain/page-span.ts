/**
 * 工具结果正文里的页标（`[page: N]`）解析。
 *
 * **为什么只给 `tool_result` 用，绝不用在 assistant 正文**：页标是本地解析器
 * 写在每页/每段开头的机器标记，模型读得到也**可能原样复述**。如果拿它切
 * assistant 正文，模型随手写的一句 `[page: 3]` 就会被当成分页符，把一句话从
 * 中间劈开、还把文字吃掉——正文里那个方括号必须原样显示。
 *
 * **为什么要把页标从文本里剔除**：解析器把标记和正文放在同一个字符串里，
 * 直接渲染就会在材料原文中间冒出 `[page: 12]` 这种噪音；律师读到的应该是
 * 干净原文 + 一行「第 12 段（按解析分段）」（措辞见 `pageSpanNote`）。
 *
 * 注意：页号是**解析器给的分段序号**，不是打印页码，展示时必须走
 * `pageSpanNote(page, kind)`，不要自己拼「第 N 页」。
 */

/** 页标：`[page: 12]`，容忍空格与大小写（解析器换实现时不至于整页失效） */
const PAGE_MARK = /\[page:\s*(\d{1,6})\s*\]/gi

/** 一段带页归属的原文 */
export interface PageSpan {
  /** 页号；整段没有页标时为 `undefined`（老数据 / 解析器没写页标） */
  page?: number
  /** 已剔除页标的正文（首尾空白已裁掉） */
  text: string
}

/**
 * 按 `[page: N]` 把工具结果切成若干段，页标本身从 `text` 里剔除。
 *
 * - 没有页标 → 单段 `{ page: undefined, text }`（老数据不特殊处理，照常渲染）
 * - 空段（连续页标之间没内容）直接丢弃，避免渲染出一堆空壳
 * - 同一页被切了两段（解析器分块）→ 合并回一段，别让「第 3 段」出现两次
 * - 整段都是空白 → 返回空数组，调用方据此不渲染（没有原文可看）
 */
export function splitPageSpans(text: string): PageSpan[] {
  const spans: PageSpan[] = []
  PAGE_MARK.lastIndex = 0

  /** 追加一段，顺带裁空白、并合并相邻同页 */
  const push = (chunk: string, page: number | undefined) => {
    const trimmed = chunk.trim()
    if (trimmed.length === 0) return
    const last = spans[spans.length - 1]
    if (last !== undefined && last.page === page) {
      last.text = `${last.text}\n${trimmed}`
      return
    }
    spans.push({ page, text: trimmed })
  }

  let page: number | undefined
  let cursor = 0
  let match = PAGE_MARK.exec(text)
  while (match !== null) {
    push(text.slice(cursor, match.index), page)
    page = Number(match[1])
    cursor = match.index + match[0].length
    match = PAGE_MARK.exec(text)
  }
  push(text.slice(cursor), page)

  return spans
}
