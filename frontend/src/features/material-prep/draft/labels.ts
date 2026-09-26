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

/** 页码区间的人类可读标签：单源 "P1–3,P5"，跨源 "甲.pdf P1,2 + 乙.pdf P3" */
export function rangeLabel(mats: BundleMat[], refs: PageKey[]): string {
  const byM: Record<number, number[]> = {}
  refs.forEach((r) => {
    ;(byM[r.mi] = byM[r.mi] || []).push(r.p)
  })
  const single = Object.keys(byM).length === 1
  return Object.keys(byM)
    .map((k) => {
      const mi = Number(k)
      const ps = (byM[mi] || []).slice().sort((a, b) => a - b)
      const parts: string[] = []
      let st = ps[0]
      let prev = ps[0]
      for (let i = 1; i <= ps.length; i++) {
        if (i < ps.length && ps[i] === prev + 1) {
          prev = ps[i]
          continue
        }
        parts.push(st === prev ? `P${st}` : `P${st}–${prev}`)
        if (i < ps.length) st = prev = ps[i]
      }
      return (single ? '' : matLabel(mats, mi) + ' ') + parts.join(',')
    })
    .join(' + ')
}

export function countUnclassified(d: DraftState): number {
  return d.segs.filter((s) => !s.t).length
}

/** 段是否覆盖整个单一源文件（用于左栏「整份」行） */
export function isWholeMat(d: DraftState, si: number): boolean {
  const sg = d.segs[si]
  if (!sg || segMats(sg).length !== 1) return false
  const mi = sg.refs[0].mi
  const m = d.mats[mi]
  if (!m) return false
  const full = new Set<number>()
  for (let p = 1; p <= m.pages; p++) full.add(p)
  const have = new Set(sg.refs.map((r) => r.p))
  return full.size === have.size && [...have].every((p) => full.has(p))
}
