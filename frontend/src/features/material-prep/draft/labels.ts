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

/* ------------------------------------------------------------------ 默认命名 */

const EXT_RE = /\.[^.]+$/

function splitName(label: string): { base: string; ext: string } {
  const m = label.match(EXT_RE)
  return { base: label.replace(EXT_RE, ''), ext: m ? m[0] : '.pdf' }
}

/**
 * 段的默认名：整份 = 源文件名；非整份 = 「源名-P起始页.ext」（跨源取首页所在的源）。
 *
 * 切开 / 切出 / 合并 / 删页四条路径共用这一条规则。以前只有「切出」的新段带 -P 后缀，
 * 切开留下的尾段和合并留下的余段都直接沿用源文件名——切三刀就有三份同名材料，
 * 左栏看起来像凭空冒出一堆同名文件。
 */
export function defaultSegName(d: DraftState, refs: PageKey[], whole: boolean): string {
  const first = refs[0]
  if (!first) return '材料.pdf'
  const label = matLabel(d.mats, first.mi)
  if (whole) return label
  const { base, ext } = splitName(label)
  return `${base}-P${first.p}${ext}`
}

/** 名字是否仍是系统默认名（某个源文件名本身，或「源名-P数字.ext」）；用户手改过的不算 */
export function isAutoSegName(d: DraftState, fn: string): boolean {
  return d.mats.some((_, mi) => {
    const label = matLabel(d.mats, mi)
    if (fn === label) return true
    const { base, ext } = splitName(label)
    if (!fn.startsWith(`${base}-P`) || !fn.endsWith(ext)) return false
    return /^\d+$/.test(fn.slice(base.length + 2, fn.length - ext.length))
  })
}

/**
 * 刷新所有仍用默认名的段：页区间变了（切开 / 切出 / 合并 / 删页）名字跟着变，
 * 变回整份就变回源文件名；用户改过名的段原样保留。无变化返回原引用。
 */
export function withDefaultNames(d: DraftState): DraftState {
  let changed = false
  const segs = d.segs.map((sg, si) => {
    if (!isAutoSegName(d, sg.fn)) return sg
    const fn = defaultSegName(d, sg.refs, isWholeMat(d, si))
    if (fn === sg.fn) return sg
    changed = true
    return { ...sg, fn }
  })
  return changed ? { ...d, segs } : d
}

/* ------------------------------------------------------------------ 页区间 */

/** 页区间文案：单源连续「P5–19」、断续「P3, P7–9」、跨源「跨源」。左栏行与段头共用 */
export function segRangeText(sg: Segment): string {
  if (!sg.refs.length) return ''
  if (segMats(sg).length !== 1) return '跨源'
  const runs: string[] = []
  let start: number | undefined
  let end: number | undefined
  const flush = () => {
    if (start === undefined || end === undefined) return
    runs.push(start === end ? `P${start}` : `P${start}–${end}`)
  }
  for (const { p } of sg.refs) {
    if (end !== undefined && p === end + 1) {
      end = p
      continue
    }
    flush()
    start = end = p
  }
  flush()
  return runs.join(', ')
}
