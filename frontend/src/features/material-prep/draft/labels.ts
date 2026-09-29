import type { BundleMat, DraftState, PageKey, Segment } from '../types'

/**
 * 纯展示标签 / 汇总统计：无 DraftState 改写，供左栏、卡片、清单、进度复用。
 */

export function matLabel(mats: BundleMat[], mi: number): string {
  return mats[mi]?.customName || mats[mi]?.n || `材料 ${mi + 1}`
}

export function segMats(sg: Segment): number[] {
  return [...new Set(sg.refs.map((r) => r.mi))]
}

/** 页面唯一键（用于选中集合） */
export const selKeyOf = (r: PageKey): string => `${r.mi}:${r.p}`

export function countUnclassified(d: DraftState): number {
  return d.segs.filter((s) => !s.t).length
}

/** 段是否覆盖整个单一源文件（用于左栏「整份」行） */
export function isWholeMat(d: DraftState, si: number): boolean {
  const sg = d.segs[si]
  if (!sg || segMats(sg).length !== 1) return false
  const mi = sg.refs[0]!.mi // 非空由上一行 segMats === 1 保证（mats 由 refs 派生）
  const m = d.mats[mi]
  if (!m) return false
  const full = new Set<number>()
  for (let p = 1; p <= m.pages; p++) full.add(p)
  const have = new Set(sg.refs.map((r) => r.p))
  return full.size === have.size && [...have].every((p) => full.has(p))
}
