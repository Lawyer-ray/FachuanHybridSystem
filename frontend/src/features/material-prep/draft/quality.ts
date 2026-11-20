import type { DocMissing, Inconsistency, PageQuality, Segment } from '../types'

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
  const quality: PageQuality = {
    graphic_pages: numList(src.graphic_pages),
    sparse_pages: numList(src.sparse_pages),
    blank_pages: numList(src.blank_pages),
    details: strMap(src.details),
    doc_hints: strMap(src.doc_hints),
    doc_missing: readDocMissing(src.doc_missing),
  }
  // 全空就当没有：让调用方少一层「有没有内容」的判断。
  // doc_missing 也算内容：它可能单独出现（知道缺什么、没给类型码），丢了就整张清单消失。
  const empty =
    quality.graphic_pages!.length === 0 &&
    quality.sparse_pages!.length === 0 &&
    quality.blank_pages!.length === 0 &&
    Object.keys(quality.doc_hints!).length === 0 &&
    Object.keys(quality.doc_missing!).length === 0
  return empty ? null : quality
}

/** `{页号: 字符串}` 的收窄：非字符串 / 空串一律丢（空串等于没提示，留着只添乱） */
function strMap(raw: unknown): Record<string, string> {
  const out: Record<string, string> = {}
  if (!raw || typeof raw !== 'object') return out
  for (const [page, text] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof text === 'string' && text) out[page] = text
  }
  return out
}

/**
 * `{页号: {doc, missing}}` 的收窄。
 *
 * 逐条校验而不是整体 `as`：旧任务没有该键、后端也可能改字段名，一条坏数据不该
 * 让整张待补录清单消失。
 *
 * 注意 `missing: []` **不丢**：后端把它作为「类型认出来了、字段也在，但整页内容
 * 可疑（如满是乱码）」的信号（见 p42 实测）。里没有字段列表不代表可以放过这一页。
 */
function readDocMissing(raw: unknown): Record<string, DocMissing> {
  const out: Record<string, DocMissing> = {}
  if (!raw || typeof raw !== 'object') return out
  for (const [page, item] of Object.entries(raw as Record<string, unknown>)) {
    if (!item || typeof item !== 'object') continue
    const r = item as Record<string, unknown>
    const missing = Array.isArray(r.missing)
      ? r.missing.filter((x): x is string => typeof x === 'string' && !!x)
      : []
    out[page] = { doc: typeof r.doc === 'string' ? r.doc : '', missing }
  }
  return out
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
      // 判据种类必须一起收窄：这里是逐键重建对象，漏掉它抽屉就永远看不到 kind，
      // 姓名聚类会被当成「疑似错字」渲染（律师可能把两个真人合并成一个）
      kind: typeof r.kind === 'string' ? r.kind : undefined,
    })
  }
  return out
}

/** 不一致的判据种类（后端逐条给 kind；文案与「哪个写法对」的语义都随它变） */
export type InconsistencyKind = 'frequency' | 'entity_cluster' | 'id_malformed'

/**
 * 判据种类收窄：**缺失 / 未知一律按 frequency**。
 *
 * 旧任务产物与旧草稿没有 kind 键，那时后端只有频次悬殊这一条判据，按 frequency
 * 处理与历史行为逐字一致；后端将来加新判据时也不至于让整张清单崩掉。
 */
export function inconsistencyKindOf(item: Pick<Inconsistency, 'kind'>): InconsistencyKind {
  return item.kind === 'entity_cluster' || item.kind === 'id_malformed' ? item.kind : 'frequency'
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

/**
 * 某段覆盖到的证件页：`{页号: 证件类型码}`，按段内页序（跨源重复页号保留两次）。
 *
 * 与 `graphicPagesOf` 同口径——跳转要的是「段里那一页」，不是全局唯一页号。
 */
export function docHintPagesOf(
  seg: Pick<Segment, 'refs'> | null | undefined,
  quality: PageQuality | null,
): { page: number; doc: string; missing: string[] }[] {
  if (!seg) return []
  const hints = quality?.doc_hints
  if (!hints) return []
  const missings = quality?.doc_missing ?? {}
  return seg.refs.flatMap((r) => {
    const doc = hints[String(r.p)]
    if (!doc) return []
    // 带上该页的缺失字段：调用方要按「有没有缺」分档提示。
    // 不带的话，只能对「字段都在」的证件页也写「关键字段可能未读出」——那是撒谎，
    // 律师翻原图发现字段好好的，以后就不信这个提示了。
    return [{ page: r.p, doc, missing: missings[String(r.p)]?.missing ?? [] }]
  })
}

/**
 * 证件类型码 → 中文名。未知码原样显示，不丢信息
 * （后端将来加 `bank_statement` 之类，前端不改也能看懂是什么）。
 *
 * 文案必须与后端 `doc_type._DOC_LABELS` **逐字一致**。同一个证件在提示条里叫「结婚证」、
 * 在抽屉里叫「婚姻状况证明」，律师会以为是两样材料。两处都改时记得同步——
 * 这是前端唯一一处复制后端文案的地方，等后端把 label 也透出到 `doc_missing`
 * 就可以删掉这份常量。
 */
export function docTypeLabel(code: string): string {
  switch (code) {
    case 'id_card':
      return '身份证'
    case 'household':
      return '户口簿'
    case 'marriage':
      return '结婚证'
    case 'property_cert':
      return '不动产权证'
    case 'license':
      return '营业执照'
    case 'income_proof':
      return '收入证明'
    default:
      return code
  }
}

/** 一页证件材料的待补录条目（清单与提示条共用） */
export interface DocTodo {
  page: number
  /** 证件类型码（原文，供比对用） */
  doc: string
  /** 中文类型名（`docTypeLabel`） */
  label: string
  /** 未读出的字段名；空数组 = 字段都在但内容可疑 */
  missing: string[]
}

/**
 * 全卷「证件页待补录」清单，按缺失字段数量降序。
 *
 * 这是律师真正会用的那张清单：打开就知道该翻哪几页、该抄什么。
 * 排序用缺失字段数（多的在前）——3 个字段全没读出的身份证比只缺一个编号的
 * 不动产权证更急；数量相同时按页号，保证顺序稳定、翻卷时不跳来跳去。
 *
 * 数据源是 `doc_missing`：后端只把 `doc_hint` 非空的页写进去，所以有 `doc_hints`
 * 但没进 `doc_missing` 的页（识别得干净、无需补录）不进清单。
 */
export function docTodosOf(quality: PageQuality | null): DocTodo[] {
  if (!quality) return []
  const hints = quality.doc_hints ?? {}
  const missings = quality.doc_missing ?? {}
  const out: DocTodo[] = []
  for (const [key, entry] of Object.entries(missings)) {
    const page = Number(key)
    if (!Number.isFinite(page) || page <= 0) continue
    const doc = entry.doc || hints[key] || ''
    out.push({
      page,
      doc,
      label: doc ? docTypeLabel(doc) : '证件页',
      missing: entry.missing ?? [],
    })
  }
  return out.sort((a, b) => b.missing.length - a.missing.length || a.page - b.page)
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

/* ============================================================
 * 段级复核：`review_flag` → 人话
 * ============================================================ */

/** 一段的复核信号归一后的形状（供段头徽标 / 左栏 tooltip / 右栏提示条共用） */
export interface SegmentReviewHint {
  /** 短标签：「建议复核」/「未识别」/「OCR 失败」 */
  label: string
  /** 为什么被标出来。拿不到具体原因时给空串——**不编原因**比编一条更可信 */
  reason: string
}

/** 后端 `PdfSplitReviewFlag` 的本地兜底文案（API 带了 `review_flag_label` 时优先用它） */
const REVIEW_LABELS: Record<string, string> = {
  low_confidence: '建议复核',
  unrecognized: '未识别',
  ocr_failed: 'OCR 失败',
}

/**
 * 分段来源 → 「为什么这一段让人不放心」。
 *
 * 取值来自后端分段侧：规则引擎 `rule` / `layout_title` / `rule_weak_only` /
 * `rule_adjacent_start` / `rule_merged_adjacent` / `gap_fill`，模型侧 `llm`。
 * 只解释**会产生 low_confidence 的那几种**，其余返回空串而不是硬凑一句。
 */
function reviewReasonOfMethod(method: string | undefined): string {
  switch (method) {
    case 'layout_title':
      return '起点是按版面标题推断的，可能把上一份的末尾切进来'
    case 'rule_weak_only':
      return '只命中了弱规则（标题像、版式不像）'
    case 'rule_adjacent_start':
      return '和上一段的起点只隔一页，可能切得太碎'
    case 'rule_merged_adjacent':
      return '和相邻段拼过再拆开，边界可能偏'
    case 'gap_fill':
      return '这段是补空得来的（前后都没有明确标题）'
    case 'llm':
    case 'llm_merged':
      return '模型对这一段的边界把握不大'
    default:
      return ''
  }
}

/**
 * 是否需要复核、为什么。
 *
 * ## 为什么要在这一层算
 *
 * 同一句话要出现在三处：中栏段头徽标、左栏段行 tooltip、右栏正文面板顶部提示条。
 * 三处各拼一遍文案，迟早出现「徽标说 62%，提示条说 60%」这种自相矛盾——律师
 * 一旦发现两处对不上，就会连带不信第三处。所以只在这里拼，组件只做展示。
 *
 * ## 为什么 low_confidence 的原因要看 `sourceMethod`
 *
 * 「建议复核」本身不构成行动：律师要知道的是**核对什么**。低置信度有四五种成因
 * （版面标题猜的起点、只命中弱规则、和上一段只隔一页……），对应的核对动作完全不同。
 */
export function reviewHintOf(seg: {
  reviewFlag?: string
  confidence?: number
  sourceMethod?: string
  reviewFlagLabel?: string
}): SegmentReviewHint | null {
  const flag = seg.reviewFlag
  if (!flag || flag === 'normal') return null
  const label = seg.reviewFlagLabel || REVIEW_LABELS[flag] || flag

  if (flag === 'low_confidence') {
    const pct =
      typeof seg.confidence === 'number' && Number.isFinite(seg.confidence)
        ? `自动分段置信度 ${Math.round(seg.confidence * 100)}%`
        : ''
    const reason = [reviewReasonOfMethod(seg.sourceMethod), pct].filter(Boolean).join(' · ')
    return { label, reason }
  }
  if (flag === 'unrecognized') return { label, reason: '这一段没认出是哪类材料，可能是模板里没有的新类型' }
  if (flag === 'ocr_failed') return { label, reason: '这一段的文字没有取出来，正文可能是空的' }
  // 后端将来新增的取值：原样展示标签，原因留空（不编）
  return { label, reason: '' }
}
