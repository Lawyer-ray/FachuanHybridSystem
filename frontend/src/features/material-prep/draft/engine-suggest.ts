import type { EngineDisagreement, Inconsistency } from '../types'

/**
 * 「更推荐改成什么」的建议。
 *
 * ## 数据来源
 *
 * 后端 `cross_page_consistency.find_inconsistencies` 会统计**全卷**里同一实体的
 * 不同写法：出现 73 次的「示例正确名」 vs 出现 3 次的「示例错写名」，后者大概率是 OCR 错字。
 * 这份统计本来只给「跨页不一致」抽屉用，这里复用成分歧的推荐依据。
 *
 * ## 为什么只认 `confidence === 'high'`
 *
 * 低置信度意味着低频写法也出现过好几次，可能**两个都是真实存在的不同人**
 * （一份卷宗里出现「示例正确名」「另一个人」两位当事人完全正常）。这时给「建议改成
 * 示例正确名」会把正确的人名改错——比不给建议糟得多。
 *
 * ## 为什么不做模糊匹配
 *
 * 只认**完全相等**（或该写法作为子串出现在引擎文本里）。不做编辑距离、不做同音
 * 推断：姓名差一个字在法律文书里可能是完全不同的人，猜错代价远大于省下的打字。
 *
 * ## 空就是空
 *
 * 没有命中就返回 null，UI 什么都不显示。不猜、不给「可能」「疑似」这类含糊提示。
 */
export interface EngineSuggestion {
  /** 建议采用的写法（全卷高频的那个） */
  canonical: string
  /** 高频写法出现的次数 */
  canonicalCount: number
  /** 当前这侧引擎文本里的低频写法 */
  variant: string
  /** 低频写法出现的次数 */
  variantCount: number
}

/**
 * 给某个引擎的这一行文本找推荐写法。
 *
 * @param text 该引擎识别出的这一行
 * @param inconsistencies 全卷不一致统计（`summary.inconsistencies`）
 */
export function suggestionFor(text: string, inconsistencies: readonly Inconsistency[]): EngineSuggestion | null {
  const body = text.trim()
  if (!body) return null

  let best: EngineSuggestion | null = null
  for (const item of inconsistencies) {
    // 只信高置信度：低频写法也出现多次时，可能两个都是真实实体（两个人、两家公司）
    if (item.confidence !== 'high') continue
    const variant = (item.variant ?? '').trim()
    const canonical = (item.canonical ?? '').trim()
    if (!variant || !canonical) continue
    if (!body.includes(variant)) continue
    // 已有更匹配的（更重要或更靠前）就跳过；这里取第一个命中的高置信度就够了，
    // 同一条文本同时命中多个变体的情形极罕见，且排序依据不明确。
    best = {
      canonical,
      canonicalCount: item.canonical_count,
      variant,
      variantCount: item.variant_count,
    }
    break
  }
  return best
}

/**
 * 一条分歧里，两侧各自的推荐写法。
 *
 * 返回空对象表示「没有任何可推荐」——UI 据此不显示提示区，而不是显示空框。
 */
export function suggestionsOf(
  item: EngineDisagreement,
  inconsistencies: readonly Inconsistency[],
): Record<string, EngineSuggestion> {
  const out: Record<string, EngineSuggestion> = {}
  for (const v of item.variants) {
    const s = suggestionFor(v.text, inconsistencies)
    if (s) out[v.engine] = s
  }
  return out
}
