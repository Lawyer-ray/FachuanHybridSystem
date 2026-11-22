import type { EngineDisagreement } from '../../types'
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
 * 逐页的「需要核对」提示：证件页缺字段 / 疑似图纸页。
 *
 * 与引擎分歧同一落点（该页正文第一行之前）——律师读到哪一页就看到那一页的问题，
 * 不用回栏顶比页号再找位置。
 *
 * 落不到任何一行的页（图纸页往往一个字都没取出来）单独补在正文之后：那一页本来
 * 就「没东西可读」，提示只能自己成一行，否则就等于没提示。
 */
export function groupDocHintsByPage(params: {
  docPages: DocHintPage[]
  graphicPages: number[]
  /** 正文行（只用它的 page 字段） */
  blocks: { page: number }[]
}): {
  /** 页号 → 该页的证件页提示（同页只取第一条） */
  docByPage: Map<number, DocHintPage>
  /** 疑似图纸/照片页 */
  graphicPages: Set<number>
  /** 该页有提示（证件页 或 图纸页）才渲染提示条 */
  hintedPages: number[]
  /** 有提示、但该页一行正文都没有的页号（按页号升序） */
  orphanHintPages: number[]
} {
  const { docPages, graphicPages, blocks } = params
  const docByPage = new Map<number, DocHintPage>()
  for (const d of docPages) {
    if (!docByPage.has(d.page)) docByPage.set(d.page, d)
  }
  const graphicSet = new Set(graphicPages)
  const hintedPages = [...new Set([...docByPage.keys(), ...graphicSet])].sort((a, b) => a - b)
  const pagesWithRows = new Set(blocks.map((b) => b.page))
  return {
    docByPage,
    graphicPages: graphicSet,
    hintedPages,
    orphanHintPages: hintedPages.filter((p) => !pagesWithRows.has(p)),
  }
}
