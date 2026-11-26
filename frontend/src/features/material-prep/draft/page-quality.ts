/**
 * 页级识别质量：把 `summary.page_quality`（自由字典）收窄成明确结构，并派生
 * 「某段覆盖了哪些图形页 / 稀疏页 / 证件页」与待补录清单。
 *
 * 组件不直接读 `summary`：旧任务里根本没有这个键，三处消费方各自强转迟早白屏。
 *
 * 收窄出来的是**一份 PDF** 的结果，草稿里按源（`mi`）分槽存（`PageQualityByMi`）；
 * 所以下面的派生函数都要拿到 `byMi`，逐条按 `ref.mi` 查对应源再判 `ref.p`。
 */
import type { DocMissing, PageQuality, PageQualityByMi, Segment } from '../types'

function numList(v: unknown): number[] {
  if (!Array.isArray(v)) return []
  return v.filter((n): n is number => typeof n === 'number' && Number.isFinite(n))
}

/** 把 `summary.page_quality`（自由字典）收窄；没有该键时返回 null，调用方据此整块不渲染 */
export function readPageQuality(raw: unknown): PageQuality | null {
  if (!raw || typeof raw !== 'object') return null
  const src = raw as Record<string, unknown>
  const graphicPages = numList(src.graphic_pages)
  const sparsePages = numList(src.sparse_pages)
  const blankPages = numList(src.blank_pages)
  const ocrFailedPages = numList(src.ocr_failed_pages)
  const docHints = strMap(src.doc_hints)
  const docMissing = readDocMissing(src.doc_missing)
  // 全空就当没有：让调用方少一层「有没有内容」的判断。
  // doc_missing 也算内容：它可能单独出现（知道缺什么、没给类型码），丢了就整张清单消失。
  // ocr_failed_pages 同理：它可能**单独**出现在一份其余完全干净的任务里（就是那几页没读到）。
  const empty =
    graphicPages.length === 0 &&
    sparsePages.length === 0 &&
    blankPages.length === 0 &&
    ocrFailedPages.length === 0 &&
    Object.keys(docHints).length === 0 &&
    Object.keys(docMissing).length === 0
  if (empty) return null
  return {
    graphic_pages: graphicPages,
    sparse_pages: sparsePages,
    blank_pages: blankPages,
    ocr_failed_pages: ocrFailedPages,
    details: strMap(src.details),
    doc_hints: docHints,
    doc_missing: docMissing,
  }
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

/** 某个源（`mi`）那一槽的页级质量；没这一槽就是 null（旧草稿 / 这一份没跑到）。
 *
 *  这是「多份 PDF 的 P5 各归各」的唯一入口：只拿**页号**去比，A 份的 P5 信号就会贴到
 *  B 份的 P5 上（页号各自从 1 开始）。 */
export function qualityOf(byMi: PageQualityByMi | null | undefined, mi: number): PageQuality | null {
  return byMi?.[String(mi)] ?? null
}

/** 按源（`mi`）预处理成「哪些页命中」：一次构建，多次按段过滤，避免 O(refs × 页号数) */
function pageSets(
  byMi: PageQualityByMi | null | undefined,
  key: 'graphic_pages' | 'ocr_failed_pages' | 'sparse_pages',
): Map<number, Set<number>> {
  const out = new Map<number, Set<number>>()
  if (!byMi) return out
  for (const [k, quality] of Object.entries(byMi)) {
    const mi = Number(k)
    const pages = quality?.[key] ?? []
    if (!Number.isFinite(mi) || pages.length === 0) continue
    out.set(mi, new Set(pages))
  }
  return out
}

/** 段内引用命中的页（**按 `seg.refs` 位置**取值，跨源合并段的重复页号会保留两次：
 *  跳转要的是「段里那一页」）。按 `ref.mi` 查源，所以 A 份的 P5 不会跑到 B 份的 P5 上。 */
function pagesMatching(
  seg: Pick<Segment, 'refs'> | null | undefined,
  sets: Map<number, Set<number>>,
): number[] {
  if (!seg) return []
  const out: number[] = []
  for (const ref of seg.refs) {
    if (sets.get(ref.mi)?.has(ref.p)) out.push(ref.p)
  }
  return out
}

/** 某段覆盖的图形页（按段内页序）。
 *
 *  跨源合并段的 refs 可能来自不同源，页号会重复；这里按**位置**取值而不是按页码
 *  过滤，保证返回的页号与 `seg.refs` 一一对应（跳转要用）。 */
export function graphicPagesOf(
  seg: Pick<Segment, 'refs'> | null | undefined,
  byMi: PageQualityByMi | null | undefined,
): number[] {
  return pagesMatching(seg, pageSets(byMi, 'graphic_pages'))
}

/** 某段覆盖的**取字失败**页（一个字都没读到，正文里根本没有这几页）。
 *
 *  与 `graphicPagesOf` 同口径（按 `seg.refs` 位置取值、允许跨源重复页号），
 *  但语义完全不同：图形页是「有图没字」，取字失败是「连一次都没成功」。
 *  后者在正文里没有任何痕迹（空页不会出现在 Markdown），因此界面上必须有
 *  一个不属于「正文内提示」的入口——左栏段行徽标就是这个入口。
 */
export function ocrFailedPagesOf(
  seg: Pick<Segment, 'refs'> | null | undefined,
  byMi: PageQualityByMi | null | undefined,
): number[] {
  return pagesMatching(seg, pageSets(byMi, 'ocr_failed_pages'))
}

/** 某段覆盖的稀疏页（有字但少得可疑：一张图上的几个字、被拍糊的一页） */
export function sparsePagesOf(
  seg: Pick<Segment, 'refs'> | null | undefined,
  byMi: PageQualityByMi | null | undefined,
): number[] {
  return pagesMatching(seg, pageSets(byMi, 'sparse_pages'))
}

/** 某段覆盖到的一页证件材料（页号 + 证件类型码 + 该页缺的字段） */
export interface DocHintPage {
  /** 哪个源：页号在多份 PDF 之间会重复，与 `DocTodo.mi` 对账要用它 */
  mi: number
  page: number
  doc: string
  /** 未读出的字段；空数组 = 类型认出来了但说不出缺哪个字段 */
  missing: string[]
}

/**
 * 某段覆盖到的证件页：`{ mi, 页号, 证件类型码, 缺字段 }`，按段内页序（跨源重复页号保留两次）。
 *
 * 与 `graphicPagesOf` 同口径——跳转要的是「段里那一页」，不是全局唯一页号；
 * 每一页按 `ref.mi` 查**自己那一份**的质量，A 份的证件页不会贴到 B 份。
 */
export function docHintPagesOf(
  seg: Pick<Segment, 'refs'> | null | undefined,
  byMi: PageQualityByMi | null | undefined,
): DocHintPage[] {
  if (!seg) return []
  const out: DocHintPage[] = []
  for (const ref of seg.refs) {
    const quality = qualityOf(byMi, ref.mi)
    const doc = quality?.doc_hints?.[String(ref.p)]
    if (!doc) continue
    // 带上该页的缺失字段：调用方要按「有没有缺」分档提示。
    // 不带的话，只能对「字段都在」的证件页也写「关键字段可能未读出」——那是撒谎，
    // 律师翻原图发现字段好好的，以后就不信这个提示了。
    out.push({ mi: ref.mi, page: ref.p, doc, missing: quality?.doc_missing?.[String(ref.p)]?.missing ?? [] })
  }
  return out
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
  /** 哪个源：页号在多份 PDF 之间会重复，去重键必须带上它（`${mi}:${page}`） */
  mi: number
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
 *
 * 多份 PDF 各自从 1 开始编页，所以每条都带 `mi`；数量相同时先按源、再按页号，
 * 保证顺序稳定（翻卷时不跳来跳去）。
 */
export function docTodosOf(byMi: PageQualityByMi | null | undefined): DocTodo[] {
  const out: DocTodo[] = []
  if (!byMi) return out
  for (const [key, quality] of Object.entries(byMi)) {
    const mi = Number(key)
    if (!Number.isFinite(mi) || !quality) continue
    const hints = quality.doc_hints ?? {}
    for (const [pageKey, entry] of Object.entries(quality.doc_missing ?? {})) {
      const page = Number(pageKey)
      if (!Number.isFinite(page) || page <= 0) continue
      const doc = entry.doc || hints[pageKey] || ''
      out.push({
        mi,
        page,
        doc,
        label: doc ? docTypeLabel(doc) : '证件页',
        missing: entry.missing ?? [],
      })
    }
  }
  return out.sort((a, b) => b.missing.length - a.missing.length || a.mi - b.mi || a.page - b.page)
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

/**
 * 数字数组收窄（`pairs.ts` 也用）：非数字 / NaN / Infinity 一律丢。
 *
 * 导出仅限 draft 内部模块共用，不经 barrel 对外。
 */
export { numList }
