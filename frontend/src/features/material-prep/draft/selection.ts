import type { DraftState, PageKey, Segment } from '../types'
import { matLabel, segMats } from './labels'

/**
 * 选页 → 独立 / 合并 / 删除编排。所有运算基于「扁平页序」，保证跨段连续性判定一致。
 */

/** 全量页面扁平列表（按段依序展开），选页区间 / 连续性判定都基于它 */
export interface FlatRef {
  si: number
  k: number
  ref: PageKey
}

export function flatRefs(d: DraftState): FlatRef[] {
  const flat: FlatRef[] = []
  d.segs.forEach((sg, si) => sg.refs.forEach((r, k) => flat.push({ si, k, ref: r })))
  return flat
}

export function pageIndexOf(d: DraftState, mi: number, p: number): number {
  return flatRefs(d).findIndex((f) => f.ref.mi === mi && f.ref.p === p)
}

/** 新段默认名：单源用源文件名当底，跨源用当前段名；带起始页，切第二次不叠后缀 */
function splitBase(sg: Segment, mats: DraftState['mats']): string {
  const mis = segMats(sg)
  const name = mis.length === 1 ? matLabel(mats, mis[0]) : sg.fn
  return name.replace(/\.[^.]+$/, '')
}
function splitExt(sg: Segment): string {
  return (sg.fn.match(/\.[^.]+$/) || ['.pdf'])[0]
}

/**
 * 把选中的若干页从所在段里「切出来」独立成一份新材料。
 * 选中页必须在顺序上是连续的（由调用方保证）。
 */
export function splitOutPages(d: DraftState, picked: PageKey[]): DraftState {
  if (!picked.length) return d
  const flat = flatRefs(d)
  const idx = picked
    .map((o) => flat.findIndex((f) => f.ref.mi === o.mi && f.ref.p === o.p))
    .filter((i) => i >= 0)
    .sort((a, b) => a - b)
  if (!idx.length) return d
  const a = idx[0]
  const b = idx[idx.length - 1]
  if (b - a + 1 !== idx.length) return d // 不连续
  const slice = flat.slice(a, b + 1)
  const si = slice[0].si
  const sg = d.segs[si]
  const k0 = slice[0].k
  const k1 = slice[slice.length - 1].k
  if (k0 === 0 && k1 === sg.refs.length - 1) return d // 这就是整份材料
  const parts: Segment[] = []
  if (k0 > 0)
    parts.push({ t: sg.t, fn: sg.fn, refs: sg.refs.slice(0, k0), manual: sg.manual })
  parts.push({
    t: '',
    fn: splitBase(sg, d.mats) + '-P' + picked[0].p + splitExt(sg),
    refs: picked,
    manual: true,
  })
  if (k1 < sg.refs.length - 1)
    parts.push({ t: sg.t, fn: sg.fn, refs: sg.refs.slice(k1 + 1), manual: sg.manual })
  const segs = [...d.segs.slice(0, si), ...parts, ...d.segs.slice(si + 1)]
  return { ...d, segs }
}

/** 把选中页并成一份新的跨源材料，并从原段移除这些页（空段被清掉）。 */
export function mergePagesIntoNew(d: DraftState, picked: PageKey[]): DraftState {
  if (!picked.length) return d
  const taken = new Set(picked.map((r) => `${r.mi}:${r.p}`))
  const segs: Segment[] = []
  for (const sg of d.segs) {
    const refs = sg.refs.filter((r) => !taken.has(`${r.mi}:${r.p}`))
    if (refs.length) segs.push({ ...sg, refs })
  }
  segs.push({ t: '', fn: '合并材料.pdf', refs: picked, manual: true })
  return { ...d, segs }
}

/**
 * 合并应用选中页：全部来自同一段 → 切出独立材料；跨段 → 并成一份跨源材料。
 * 返回新的 draft（未选中不产生任何变化）。
 */
export function applyPageSelection(d: DraftState, selPages: PageKey[]): DraftState {
  if (!selPages.length) return d
  const flat = flatRefs(d)
  const idx = selPages
    .map((o) => flat.findIndex((f) => f.ref.mi === o.mi && f.ref.p === o.p))
    .filter((i) => i >= 0)
    .sort((a, b) => a - b)
  if (!idx.length) return d
  const slice = flat.slice(idx[0], idx[idx.length - 1] + 1)
  const involved = new Set(slice.map((f) => f.si))
  if (involved.size === 1) return splitOutPages(d, selPages)
  return mergePagesIntoNew(d, selPages)
}

/**
 * 选中页是否在顺序上连续（跨段 / 乱序都不算；允许跨源但在扁平序上相邻）。
 */
export function isSelectionContiguous(d: DraftState, selPages: PageKey[]): boolean {
  if (!selPages.length) return false
  const idx = selPages
    .map((o) => pageIndexOf(d, o.mi, o.p))
    .filter((i) => i >= 0)
    .sort((a, b) => a - b)
  if (!idx.length || idx.length !== selPages.length) return false
  return idx[idx.length - 1] - idx[0] + 1 === idx.length
}

/**
 * 删除选中页面：从所有段里移除这些页的引用，空段一并清理。
 * 只影响拆分草稿（后续不再引用被删页），物理 PDF 文件不动。
 */
export function removePages(d: DraftState, picked: PageKey[]): DraftState {
  if (!picked.length) return d
  const gone = new Set(picked.map((r) => `${r.mi}:${r.p}`))
  const segs = d.segs
    .map((sg) => ({ ...sg, refs: sg.refs.filter((r) => !gone.has(`${r.mi}:${r.p}`)) }))
    .filter((sg) => sg.refs.length > 0)
  if (segs.length === d.segs.length && segs.every((sg, i) => sg === d.segs[i])) return d
  return { ...d, segs }
}
