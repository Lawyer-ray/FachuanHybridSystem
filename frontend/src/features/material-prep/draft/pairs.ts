/**
 * 跨页不一致（`summary.inconsistencies`）：不可信输入的收窄 + 判据种类 + 排序。
 *
 * 与页级质量（`page-quality.ts`）互不相关：这边锁的是「同一枚章被识别成两种写法」，
 * 那边锁的是「哪几页是图 / 哪几页几乎没字」。
 */
import type { Inconsistency } from '../types'
import { numList } from './page-quality'

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

/** confidence 未知/缺失时的兜底值：既不是 high 也不是 medium，排在最后 */
const CONFIDENCE_RANK: Record<string, number> = { high: 0, medium: 1 }
const CONFIDENCE_UNKNOWN = 2

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
