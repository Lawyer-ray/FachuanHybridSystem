import type { DraftState, PageKey, Segment } from '../types'
import { matLabel, segMats } from './labels'
import { nextSegId } from './seg-id'

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

/** 一组页在扁平序中的下标（找不到的页剔除），升序返回 */
function flatIndexesOf(flat: FlatRef[], picked: PageKey[]): number[] {
  return picked
    .map((o) => flat.findIndex((f) => f.ref.mi === o.mi && f.ref.p === o.p))
    .filter((i) => i >= 0)
    .sort((a, b) => a - b)
}

/** 新段默认名：单源用源文件名当底，跨源用当前段名；带起始页，切第二次不叠后缀 */
function splitBase(sg: Segment, mats: DraftState['mats']): string {
  const mis = segMats(sg)
  // mis[0] 的非空由 length === 1 三元左侧证明
  const name = mis.length === 1 ? matLabel(mats, mis[0]!) : sg.fn
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
  const idx = flatIndexesOf(flat, picked)
  if (!idx.length) return d
  // ⌘ 点选的 picked 是「点选顺序」（先点 P5 再点 P4 会倒序传入）——落段前按
  // 扁平文档序 normalize，否则新段页序颠倒、命名起始页取的是最后点的页
  const ordered = idx.map((i) => flat[i]!.ref)
  // a / b 的非空由上一行 idx 非空守卫保证
  const a = idx[0]!
  const b = idx[idx.length - 1]!
  if (b - a + 1 !== idx.length) return d // 不连续
  const slice = flat.slice(a, b + 1)
  const si = slice[0]!.si
  const sg = d.segs[si]
  // si 来自 flatRefs 对 d.segs 的展开，正常必然命中；数据不变量破坏时原样返回
  if (!sg) return d
  const k0 = slice[0]!.k
  const k1 = slice[slice.length - 1]!.k
  if (k0 === 0 && k1 === sg.refs.length - 1) return d // 这就是整份材料
  const parts: Segment[] = []
  // 头部沿用原段 id（它顶替原段的位置），切出的新段与尾段各自取新 id
  if (k0 > 0)
    parts.push({ id: sg.id, t: sg.t, fn: sg.fn, refs: sg.refs.slice(0, k0), manual: sg.manual })
  parts.push({
    id: nextSegId(),
    t: '',
    fn: splitBase(sg, d.mats) + '-P' + ordered[0]!.p + splitExt(sg),
    refs: ordered,
    manual: true,
  })
  if (k1 < sg.refs.length - 1)
    parts.push({ id: nextSegId(), t: sg.t, fn: sg.fn, refs: sg.refs.slice(k1 + 1), manual: sg.manual })
  const segs = [...d.segs.slice(0, si), ...parts, ...d.segs.slice(si + 1)]
  return { ...d, segs }
}

/** 把选中页并成一份新的跨源材料，并从原段移除这些页（空段被清掉）。 */
export function mergePagesIntoNew(d: DraftState, picked: PageKey[]): DraftState {
  if (!picked.length) return d
  // 合并段 refs 同样按扁平文档序 normalize（点选顺序不影响成段后的页序）
  const flat = flatRefs(d)
  const ordered = flatIndexesOf(flat, picked).map((i) => flat[i]!.ref)
  const taken = new Set(picked.map((r) => `${r.mi}:${r.p}`))
  const segs: Segment[] = []
  for (const sg of d.segs) {
    const refs = sg.refs.filter((r) => !taken.has(`${r.mi}:${r.p}`))
    if (refs.length) segs.push({ ...sg, refs })
  }
  segs.push({ id: nextSegId(), t: '', fn: '合并材料.pdf', refs: ordered, manual: true })
  return { ...d, segs }
}

/**
 * 合并应用选中页：全部来自同一段 → 切出独立材料；跨段 → 并成一份跨源材料。
 * 返回新的 draft（未选中不产生任何变化）。
 */
export function applyPageSelection(d: DraftState, selPages: PageKey[]): DraftState {
  if (!selPages.length) return d
  const flat = flatRefs(d)
  const idx = flatIndexesOf(flat, selPages)
  if (!idx.length) return d
  // 首尾下标的非空由上一行守卫保证；slice 起止参数本身接受 undefined
  const slice = flat.slice(idx[0], idx[idx.length - 1]! + 1)
  const involved = new Set(slice.map((f) => f.si))
  if (involved.size === 1) return splitOutPages(d, selPages)
  return mergePagesIntoNew(d, selPages)
}

/**
 * 选中页是否在顺序上连续（跨段 / 乱序都不算；允许跨源但在扁平序上相邻）。
 */
export function isSelectionContiguous(d: DraftState, selPages: PageKey[]): boolean {
  if (!selPages.length) return false
  const idx = flatIndexesOf(flatRefs(d), selPages)
  if (!idx.length || idx.length !== selPages.length) return false
  // 首尾下标的非空由上面的长度条件保证
  return idx[idx.length - 1]! - idx[0]! + 1 === idx.length
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
