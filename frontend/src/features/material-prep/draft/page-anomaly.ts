/**
 * 页级识别风险：把 `summary.degenerate_pages`（顶层）与
 * `summary.table_geometry.column_anomalies`（嵌在 `table_geometry` 下）收窄成明确结构，
 * 并派生「某段覆盖了哪些这类页」。
 *
 * 为什么要有这一层：这两个键一个在 summary 顶层、一个埋在两层的
 * `table_geometry` 里（同一块还带 `enabled` 开关与零值键），旧任务则整块缺键。
 * 组件各自去 `summary as ...` 取值的话，漏判一处就是打开旧材料包白屏。
 * 收窄只在这里做一次，组件只读 `PageAnomaly`。
 *
 * 两件事的共同点：任务状态是成功的、正文也生成了，但机器读出来的东西本身可疑。
 * - 退化页：云端把该页读成复读循环、正文被清空，已改由本地 OCR 兜底；
 * - 列数突变：该页表格列数与邻页不同，数字表头的列可能被并/拆。
 * 两者都**不是失败**，所以不升级收尾提示的 warning（见 `summarizeAutoSplitResults`）。
 */
import type { ColumnAnomaly, PageAnomaly, PageAnomalyByMi, Segment } from '../types'
import { numList } from './page-quality'

function isNum(v: unknown): v is number {
  return typeof v === 'number' && Number.isFinite(v)
}

/**
 * `column_anomalies` 的收窄：四字段必须都是有限数字，缺一个就丢。
 *
 * 逐条校验而不是整体 `as`：画不出「第几页 vs 邻页第几页、几列 vs 几列」这条对照的
 * 条目留着只会在提示里制造一句读不懂的话。
 */
function readColumnAnomalies(raw: unknown): ColumnAnomaly[] {
  if (!Array.isArray(raw)) return []
  const out: ColumnAnomaly[] = []
  for (const item of raw) {
    if (!item || typeof item !== 'object') continue
    const r = item as Record<string, unknown>
    if (!isNum(r.page_no) || !isNum(r.prev_page_no) || !isNum(r.cols) || !isNum(r.prev_cols)) continue
    out.push({
      page_no: r.page_no,
      prev_page_no: r.prev_page_no,
      cols: r.cols,
      prev_cols: r.prev_cols,
    })
  }
  return out
}

/**
 * 把**整个 summary** 收窄成页级风险信号。
 *
 * 两者都空 → 返回 `null`，调用方据此整块不渲染（旧任务的 summary 里两个键都没有，
 * 与引入本功能前的界面逐位一致；关了表格几何开关时 `table_geometry` 里的零值键
 * 也归到这里，不该让界面出现一条空提示）。
 */
export function readPageAnomaly(summary: unknown): PageAnomaly | null {
  if (!summary || typeof summary !== 'object') return null
  const src = summary as Record<string, unknown>
  const geometry = src.table_geometry
  const columnAnomalies = readColumnAnomalies(
    geometry && typeof geometry === 'object' ? (geometry as Record<string, unknown>).column_anomalies : null,
  )
  const degeneratePages = numList(src.degenerate_pages)
  if (degeneratePages.length === 0 && columnAnomalies.length === 0) return null
  return { degenerate_pages: degeneratePages, column_anomalies: columnAnomalies }
}

/** 按源（mi）预处理出「哪些页退化」的集合：一次构建，多次按段过滤，避免 O(refs × 异常条数) */
function degenerateSets(byMi: PageAnomalyByMi | null): Map<number, Set<number>> {
  const out = new Map<number, Set<number>>()
  if (!byMi) return out
  for (const [key, value] of Object.entries(byMi)) {
    const mi = Number(key)
    const pages = value?.degenerate_pages ?? []
    if (!Number.isFinite(mi) || pages.length === 0) continue
    out.set(mi, new Set(pages))
  }
  return out
}

/** 同上，列数突变页 */
function columnSets(byMi: PageAnomalyByMi | null): Map<number, Set<number>> {
  const out = new Map<number, Set<number>>()
  if (!byMi) return out
  for (const [key, value] of Object.entries(byMi)) {
    const mi = Number(key)
    const items = value?.column_anomalies ?? []
    if (!Number.isFinite(mi) || items.length === 0) continue
    out.set(mi, new Set(items.map((item) => item.page_no)))
  }
  return out
}

/** `${mi}:${p}` → 该页的列数突变详情：一处建表，供「几列 vs 邻页几列」的文案直接查 */
function columnIndex(byMi: PageAnomalyByMi | null): Map<string, ColumnAnomaly> {
  const out = new Map<string, ColumnAnomaly>()
  if (!byMi) return out
  for (const [key, value] of Object.entries(byMi)) {
    for (const item of value?.column_anomalies ?? []) {
      out.set(`${key}:${item.page_no}`, item)
    }
  }
  return out
}

/** 段内引用命中的页（**按 `seg.refs` 位置**取值，跨源合并段的重复页号会保留两次：
 *  跳转要的是「段里那一页」；与 `ocrFailedPagesOf` 同口径）。
 *
 *  按 `ref.mi` 查源，所以「A 份的 P5 退化」不会跑到 B 份的 P5 上。 */
function pagesMatching(seg: Pick<Segment, 'refs'> | null | undefined, sets: Map<number, Set<number>>): number[] {
  if (!seg) return []
  const out: number[] = []
  for (const ref of seg.refs) {
    if (sets.get(ref.mi)?.has(ref.p)) out.push(ref.p)
  }
  return out
}

/** 某段覆盖的退化页（按段内页序） */
export function degeneratePagesOf(
  seg: Pick<Segment, 'refs'> | null | undefined,
  byMi: PageAnomalyByMi | null | undefined,
): number[] {
  return pagesMatching(seg, degenerateSets(byMi ?? null))
}

/** 某段覆盖的列数突变页（口径同上） */
export function columnAnomalyPagesOf(
  seg: Pick<Segment, 'refs'> | null | undefined,
  byMi: PageAnomalyByMi | null | undefined,
): number[] {
  return pagesMatching(seg, columnSets(byMi ?? null))
}

/** 某段覆盖的列数突变**详情**（提示里要写「5 列 vs 邻页 4 列」），按段内页序 */
export function columnAnomaliesOf(
  seg: Pick<Segment, 'refs'> | null | undefined,
  byMi: PageAnomalyByMi | null | undefined,
): ColumnAnomaly[] {
  if (!seg) return []
  const index = columnIndex(byMi ?? null)
  const out: ColumnAnomaly[] = []
  for (const ref of seg.refs) {
    const hit = index.get(`${ref.mi}:${ref.p}`)
    if (hit) out.push(hit)
  }
  return out
}

/** 单页的列数突变详情；没有就返回 null */
export function columnAnomalyOf(
  byMi: PageAnomalyByMi | null | undefined,
  mi: number,
  page: number,
): ColumnAnomaly | null {
  return columnIndex(byMi ?? null).get(`${mi}:${page}`) ?? null
}

/** 卷级统计：某段里两类风险页的 `${mi}:${p}` 键（左栏徽标要跨源去重，不能只数页号） */
export function riskPageKeysOf(
  seg: Pick<Segment, 'refs'> | null | undefined,
  byMi: PageAnomalyByMi | null | undefined,
): { degenerate: Set<string>; column: Set<string> } {
  const degenerate = new Set<string>()
  const column = new Set<string>()
  if (!seg) return { degenerate, column }
  const deg = degenerateSets(byMi ?? null)
  const col = columnSets(byMi ?? null)
  for (const ref of seg.refs) {
    const key = `${ref.mi}:${ref.p}`
    if (deg.get(ref.mi)?.has(ref.p)) degenerate.add(key)
    if (col.get(ref.mi)?.has(ref.p)) column.add(key)
  }
  return { degenerate, column }
}
