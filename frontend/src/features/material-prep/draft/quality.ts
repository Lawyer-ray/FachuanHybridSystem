import type { Inconsistency, PageQuality, Segment } from '../types'

/**
 * 识别质量提示的纯逻辑：页级质量统计 + 跨页不一致清单。
 *
 * ## 为什么需要这一层
 *
 * 后端已经在 `summary` 里给出了「哪几页是图纸、哪几页几乎没字」以及「同一枚章被
 * 识别成了两种写法」，但字段全是自由字典、旧任务里根本没有。前端消费它的地方有三处
 * （左栏段行、右栏正文面板、全局清单），如果三处各自 `summary.page_quality as ...`
 * 强转，任何一处漏判空都会在「打开一个旧材料包」时白屏。
 *
 * 所以这里只做一件事：把不可信的 `unknown` 收窄成**明确的可选结构**，再给几组
 * 派生量（某段覆盖了哪些图形页、提示文案怎么写）。组件只读收窄后的结果。
 *
 * ## 排序口径
 *
 * 不一致清单按 confidence 从高到低：high > medium > 其它（后端未给出等级时按低处理，
 * 因为「不确定」不该排在「确定可疑」前面）。同级按变体出现次数多的在前——律师只需要
 * 先看那 5 次错字，而不是 1 次的手误。
 */

/** confidence 未知/缺失时的兜底值：既不是 high 也不是 medium，排在最后 */
const CONFIDENCE_RANK: Record<string, number> = { high: 0, medium: 1 }
const CONFIDENCE_UNKNOWN = 2

function numList(v: unknown): number[] {
  if (!Array.isArray(v)) return []
  return v.filter((n): n is number => typeof n === 'number' && Number.isFinite(n))
}

/** 把 `summary.page_quality`（自由字典）收窄；没有该键时返回 null，调用方据此整块不渲染 */
export function readPageQuality(raw: unknown): PageQuality | null {
  if (!raw || typeof raw !== 'object') return null
  const src = raw as Record<string, unknown>
  const detailsRaw = src.details
  const details: Record<string, string> = {}
  if (detailsRaw && typeof detailsRaw === 'object') {
    for (const [page, text] of Object.entries(detailsRaw as Record<string, unknown>)) {
      if (typeof text === 'string' && text) details[page] = text
    }
  }
  const quality: PageQuality = {
    graphic_pages: numList(src.graphic_pages),
    sparse_pages: numList(src.sparse_pages),
    blank_pages: numList(src.blank_pages),
    details,
  }
  // 全空就当没有：让调用方少一层「有没有内容」的判断
  const empty =
    quality.graphic_pages!.length === 0 && quality.sparse_pages!.length === 0 && quality.blank_pages!.length === 0
  return empty ? null : quality
}

/**
 * 把 `summary.inconsistencies`（自由字典数组）收窄。
 *
 * 逐条校验而不是整体 `as`：旧任务 / 后端改字段都可能给出缺字段的条目，一条坏数据
 * 不该让整张清单消失，缺页号列表就当成不可跳转。
 */
export function readInconsistencies(raw: unknown): Inconsistency[] {
  if (!Array.isArray(raw)) return []
  const out: Inconsistency[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const r = item as Record<string, unknown>
    const canonical = typeof r.canonical === 'string' ? r.canonical : ''
    const variant = typeof r.variant === 'string' ? r.variant : ''
    // 两边都空（或两边同名）时这条不一致没有意义，直接丢
    if (!canonical || !variant || canonical === variant) continue
    out.push({
      canonical,
      variant,
      canonical_count: typeof r.canonical_count === 'number' ? r.canonical_count : 0,
      variant_count: typeof r.variant_count === 'number' ? r.variant_count : 0,
      pages: numList(r.pages),
      confidence: typeof r.confidence === 'string' ? r.confidence : '',
    })
  }
  return out
}

/** 清单排序：high → medium → 其它；同级变体次数多的在前，再按首个页号 */
export function sortInconsistencies(list: Inconsistency[]): Inconsistency[] {
  return [...list].sort((a, b) => {
    const ra = CONFIDENCE_RANK[a.confidence] ?? CONFIDENCE_UNKNOWN
    const rb = CONFIDENCE_RANK[b.confidence] ?? CONFIDENCE_UNKNOWN
    if (ra !== rb) return ra - rb
    if (a.variant_count !== b.variant_count) return b.variant_count - a.variant_count
    return (a.pages[0] ?? 0) - (b.pages[0] ?? 0)
  })
}

/** 某段覆盖的图形页（按段内页序）。
 *
 *  跨源合并段的 refs 可能来自不同源，页号会重复；这里按**位置**取值而不是按页码
 *  过滤，保证返回的页号与 `seg.refs` 一一对应（跳转要用）。 */
export function graphicPagesOf(
  seg: Pick<Segment, 'refs'> | null | undefined,
  quality: PageQuality | null,
): number[] {
  if (!seg) return []
  const graphics = new Set(quality?.graphic_pages ?? [])
  if (graphics.size === 0) return []
  return seg.refs.map((r) => r.p).filter((p) => graphics.has(p))
}

/** 某段覆盖的稀疏页（有字但少得可疑：一张图上的几个字、被拍糊的一页） */
export function sparsePagesOf(
  seg: Pick<Segment, 'refs'> | null | undefined,
  quality: PageQuality | null,
): number[] {
  if (!seg) return []
  const sparse = new Set(quality?.sparse_pages ?? [])
  if (sparse.size === 0) return []
  return seg.refs.map((r) => r.p).filter((p) => sparse.has(p))
}

/** 段的质量标记（后端 quality_flags）→ 一眼能懂的中文。未知标记原样显示，不丢信息 */
export function qualityFlagLabel(flag: string): string {
  switch (flag) {
    case 'graphic':
    case 'graphic_page':
      return '图形页'
    case 'sparse':
    case 'sparse_text':
      return '文字稀疏'
    case 'blank':
    case 'blank_page':
      return '空白页'
    default:
      return flag
  }
}

/** 页号压缩成区间文案：连续「P147–148」、断续「P3, P7–9」 */
export function pagesText(pages: number[]): string {
  if (pages.length === 0) return ''
  const sorted = [...new Set(pages)].sort((a, b) => a - b)
  const parts: string[] = []
  let start = sorted[0]!
  let prev = start
  for (let i = 1; i <= sorted.length; i++) {
    const cur = sorted[i]
    if (cur === prev + 1) {
      prev = cur
      continue
    }
    parts.push(start === prev ? `P${start}` : `P${start}–${prev}`)
    if (cur === undefined) break
    start = cur
    prev = cur
  }
  return parts.join(', ')
}
