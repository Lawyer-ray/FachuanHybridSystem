/**
 * 复核清单的**排序与分组**：把 `reviewItemsOf` 的产出顺序换成展示顺序。
 *
 * 排序是无损后处理，独立于信号提取（`review-items.ts`）——调用方有时要的是
 * 「按信号源分组」，只有要展示时才需要这里的全序。
 */
import type { ReviewItem, ReviewItemKind } from './review-ids'

const SEVERITY_RANK: Record<ReviewItem['severity'], number> = { high: 0, medium: 1, low: 2 }
const KIND_RANK: Record<ReviewItemKind, number> = {
  disagreement: 0,
  doc_missing: 1,
  inconsistency: 2,
  quality: 3,
  graphic: 4,
  sparse: 5,
}

/**
 * 排序：severity 降序，同 severity 按页升序。
 *
 * 同严重度同页时再按 kind 与 id 兜底：排序必须是**全序**，否则相同输入的两次调用
 * 可能给出不同顺序（后端数组顺序变了就变），列表会在律师眼皮底下跳动。
 */
export function sortReviewItems(items: ReviewItem[]): ReviewItem[] {
  return [...items].sort((a, b) => {
    const ra = SEVERITY_RANK[a.severity] ?? SEVERITY_RANK.low
    const rb = SEVERITY_RANK[b.severity] ?? SEVERITY_RANK.low
    if (ra !== rb) return ra - rb
    if (a.page !== b.page) return a.page - b.page
    const ka = KIND_RANK[a.kind] ?? 99
    const kb = KIND_RANK[b.kind] ?? 99
    if (ka !== kb) return ka - kb
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0
  })
}

/**
 * 按页分组（页号升序），页内沿用 `sortReviewItems` 的顺序。
 *
 * 抽屉与页头徽标共用这个分组：徽标上的数字就是 `items.length`，
 * 点开抽屉看到的第一组就是这一页——两边数字对上，律师才信这个计数。
 */
export function groupByPage(items: ReviewItem[]): { page: number; items: ReviewItem[] }[] {
  const sorted = sortReviewItems(items)
  const groups = new Map<number, ReviewItem[]>()
  for (const item of sorted) {
    const list = groups.get(item.page)
    if (list) list.push(item)
    else groups.set(item.page, [item])
  }
  // Map 保持插入顺序，而 sorted 已按页升序，所以这里天然是升序
  return [...groups.entries()].map(([page, list]) => ({ page, items: list }))
}
