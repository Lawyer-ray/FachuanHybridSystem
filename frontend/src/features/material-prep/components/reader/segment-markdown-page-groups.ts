import type { ColumnAnomaly, EngineDisagreement } from '../../types'
import type { DocHintPage } from './SegmentQualityHint'

/** 某一页上的引擎分歧（`items` 与 `keys` 一一对应） */
export interface DisagreementBucket {
  items: EngineDisagreement[]
  keys: string[]
}

/**
 * 分歧按页号分组：挂到该页**第一行之前**。
 *
 * 刻意不做行级精确匹配：一条分歧的「行」可能横跨多个 block（MinerU 把整页压成
 * 1 行、VL 分成几十行），`blocks[].text` 还被截断过，实测只有约 2/3 能对上。
 * 按页挂是律师真正需要的粒度——「这一页有疑问，翻过去看」，成本也低得多。
 *
 * @param pageNos 本段覆盖的页号（`seg.refs`）。段外的分歧（比如全卷口径传进来的
 *                其它页）直接丢弃：挂不上就不该显示，否则读 P3 时冒出 P9 的分歧。
 */
export function groupDisagreementsByPage(params: {
  engineItems: EngineDisagreement[]
  engineKeys: string[]
  pageNos: number[]
}): Map<number, DisagreementBucket> {
  const { engineItems, engineKeys, pageNos } = params
  const pageSet = new Set(pageNos)
  const byPage = new Map<number, DisagreementBucket>()
  engineItems.forEach((d, i) => {
    const k = engineKeys[i]
    if (!k || !pageSet.has(d.page_no)) return
    const bucket = byPage.get(d.page_no) ?? { items: [], keys: [] }
    bucket.items.push(d)
    bucket.keys.push(k)
    byPage.set(d.page_no, bucket)
  })
  return byPage
}

/**
 * 逐页的「需要核对」提示：证件页缺字段 / 疑似图纸页 / 云端取字退化页 / 表格列数突变页。
 *
 * 与引擎分歧同一落点（该页正文第一行之前）——律师读到哪一页就看到那一页的问题，
 * 不用回栏顶比页号再找位置。
 *
 * 落不到任何一行的页单独补在正文之后：那一页本来就「没东西可读」，提示只能自己成
 * 一行，否则就等于没提示。退化页**尤其**会走到这条路上——云端把整页读成复读循环时
 * 正文被清空、改由本地 OCR 兜底，这一页往往一行云端正文都没有；不纳入 orphan 就等于
 * 这条信号只在左栏有个数字，律师永远看不到它指的是哪一页。
 */
export function groupDocHintsByPage(params: {
  docPages: DocHintPage[]
  graphicPages: number[]
  /** 本段里云端取字判为退化的页（`summary.degenerate_pages`） */
  degeneratePages: number[]
  /** 本段里的表格列数突变页（`summary.table_geometry.column_anomalies`） */
  columnAnomalies: ColumnAnomaly[]
  /** 正文行（只用它的 page 字段） */
  blocks: { page: number }[]
}): {
  /** 页号 → 该页的证件页提示（同页只取第一条） */
  docByPage: Map<number, DocHintPage>
  /** 疑似图纸/照片页 */
  graphicPages: Set<number>
  /** 云端取字退化的页 */
  degeneratePages: Set<number>
  /** 页号 → 该页的列数突变详情（同页只取第一条） */
  columnAnomalyByPage: Map<number, ColumnAnomaly>
  /** 该页有提示（四类任一）才渲染提示条 */
  hintedPages: number[]
  /** 有提示、但该页一行正文都没有的页号（按页号升序） */
  orphanHintPages: number[]
} {
  const { docPages, graphicPages, degeneratePages, columnAnomalies, blocks } = params
  const docByPage = new Map<number, DocHintPage>()
  for (const d of docPages) {
    if (!docByPage.has(d.page)) docByPage.set(d.page, d)
  }
  const graphicSet = new Set(graphicPages)
  const degenerateSet = new Set(degeneratePages)
  const columnByPage = new Map<number, ColumnAnomaly>()
  for (const a of columnAnomalies) {
    // 一页一条：两句话叠在一起律师读不懂哪句对应哪种列数
    if (!columnByPage.has(a.page_no)) columnByPage.set(a.page_no, a)
  }
  const hintedPages = [
    ...new Set([...docByPage.keys(), ...graphicSet, ...degenerateSet, ...columnByPage.keys()]),
  ].sort((a, b) => a - b)
  const pagesWithRows = new Set(blocks.map((b) => b.page))
  return {
    docByPage,
    graphicPages: graphicSet,
    degeneratePages: degenerateSet,
    columnAnomalyByPage: columnByPage,
    hintedPages,
    orphanHintPages: hintedPages.filter((p) => !pagesWithRows.has(p)),
  }
}
