import type { DraftState, PageKey, PositionedBlock, Segment } from '../types'
import { defaultSegName, matLabel, segMats, withDefaultNames } from './labels'
import { blocksForPages, concatBlocks, joinMdByPages, joinWholeMd, type MdPart, type MdSlice } from './md-pages'
import { markMdMoved } from './segments'
import { nextSegId } from './seg-id'

/**
 * 选页 → 独立 / 合并 / 删除编排。所有运算基于「扁平页序」，保证跨段连续性判定一致。
 *
 * 正文与定位块跟着页走（`md-pages`）：切出去的页把正文带走，留下的页不留别页的字。
 * 页锚点缺失时的兜底口径统一为「整份正文留给保住原段首页的那一份」，其余份宁可
 * 缺正文也不凭空拿到别页内容；并段则是整份按段序拼接（不丢字）。
 */

/** 一份新段的正文与页锚点：slice 为 null 表示锚不到页，只有 fallback owner 能拿整份 */
function mdOf(slice: MdSlice | null, owner: boolean, src: Segment): Pick<Segment, 'md' | 'pageSpans'> {
  if (slice) return { md: slice.md || undefined, pageSpans: slice.pageSpans.length ? slice.pageSpans : undefined }
  return owner ? { md: src.md, pageSpans: src.pageSpans } : { md: undefined, pageSpans: undefined }
}

/** 原段首页是否还在这一份里（注入的段标题跟着首页走） */
function keepsFirstPage(src: Segment, pages: PageKey[]): boolean {
  const first = src.refs[0]
  const head = pages[0]
  return Boolean(first && head && first.mi === head.mi && first.p === head.p)
}

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
  const headRefs = sg.refs.slice(0, k0)
  const tailRefs = sg.refs.slice(k1 + 1)
  const hadMd = Boolean(sg.md)
  const headSlice = k0 > 0 ? joinMdByPages([{ seg: sg, pages: headRefs }], true) : null
  const midSlice = joinMdByPages([{ seg: sg, pages: ordered }], k0 === 0)
  const tailSlice = tailRefs.length ? joinMdByPages([{ seg: sg, pages: tailRefs }]) : null
  // 头部沿用原段 id（它顶替原段的位置），切出的新段与尾段各自取新 id
  if (k0 > 0)
    parts.push(markMdMoved({
      id: sg.id, t: sg.t, fn: sg.fn, refs: headRefs, manual: sg.manual,
      blocks: blocksForPages(sg.blocks, headRefs), ...mdOf(headSlice, true, sg),
    }, hadMd))
  parts.push(markMdMoved({
    id: nextSegId(),
    t: '',
    fn: splitBase(sg, d.mats) + '-P' + ordered[0]!.p + splitExt(sg),
    refs: ordered,
    manual: true,
    blocks: blocksForPages(sg.blocks, ordered),
    ...mdOf(midSlice, k0 === 0, sg),
  }, hadMd))
  if (tailRefs.length)
    parts.push(markMdMoved({
      id: nextSegId(), t: sg.t, fn: sg.fn, refs: tailRefs, manual: sg.manual,
      blocks: blocksForPages(sg.blocks, tailRefs), ...mdOf(tailSlice, false, sg),
    }, hadMd))
  const segs = [...d.segs.slice(0, si), ...parts, ...d.segs.slice(si + 1)]
  // 头 / 尾残段若还用着源文件名，按页区间改成「源名-P起始页」——否则切几刀就有几份同名
  return withDefaultNames({ ...d, segs })
}

/**
 * 把选中页并成一份新材料，并从原段移除这些页（空段被清掉）。
 *
 * 新段**插在首选页原来所在的位置**，不追加到末尾：以前并完的那一份会跳到整个
 * 文档最后面，页序被打乱，看起来像凭空多出一个文件而不是"并成了一份"。
 * 命名走 defaultSegName（源名-P起始页），不再叫「合并材料.pdf」。
 */
export function mergePagesIntoNew(d: DraftState, picked: PageKey[]): DraftState {
  if (!picked.length) return d
  // 合并段 refs 同样按扁平文档序 normalize（点选顺序不影响成段后的页序）
  const flat = flatRefs(d)
  const idx = flatIndexesOf(flat, picked)
  if (!idx.length) return d
  const ordered = idx.map((i) => flat[i]!.ref)
  const firstSi = flat[idx[0]!]!.si
  const taken = new Set(picked.map((r) => `${r.mi}:${r.p}`))
  // 参与合并的页按来源段分组（idx 升序 → 同段的页天然连续），正文按这个页序拼接
  const parts: MdPart[] = []
  idx.forEach((i, n) => {
    const src = d.segs[flat[i]!.si]!
    const last = parts[parts.length - 1]
    if (last && last.seg === src) last.pages.push(ordered[n]!)
    else parts.push({ seg: src, pages: [ordered[n]!] })
  })
  const slice = joinMdByPages(parts, keepsFirstPage(parts[0]!.seg, ordered))
  const blocks = parts.reduce<PositionedBlock[] | undefined>(
    (acc, p) => concatBlocks(acc, blocksForPages(p.seg.blocks, p.pages)),
    undefined,
  )
  const merged: Segment = markMdMoved({
    id: nextSegId(),
    t: '',
    fn: defaultSegName(d, ordered, false),
    refs: ordered,
    manual: true,
    blocks,
    // 锚不到页时只带走「整段都被搬走」的源段正文；只搬走部分页的源段正文留在残段
    md: slice
      ? slice.md || undefined
      : joinWholeMd(parts.filter((p) => p.seg.refs.every((r) => taken.has(`${r.mi}:${r.p}`))).map((p) => p.seg)),
    pageSpans: slice?.pageSpans.length ? slice.pageSpans : undefined,
  }, parts.some((p) => p.seg.md))
  const segs: Segment[] = []
  let inserted = false
  d.segs.forEach((sg, si) => {
    const refs = sg.refs.filter((r) => !taken.has(`${r.mi}:${r.p}`))
    if (refs.length) {
      const rest = joinMdByPages([{ seg: sg, pages: refs }], keepsFirstPage(sg, refs))
      segs.push(markMdMoved(
        { ...sg, refs, blocks: blocksForPages(sg.blocks, refs), ...mdOf(rest, true, sg) },
        Boolean(sg.md) && rest !== null,
      ))
    }
    // 首选页所在段：它剩下的页（选区之前的部分）留在前面，合并段紧随其后
    if (si === firstSi) {
      segs.push(merged)
      inserted = true
    }
  })
  if (!inserted) segs.push(merged)
  return withDefaultNames({ ...d, segs })
}

/**
 * 多选段并成一份：refs 按文档扁平序拼接（页不重排），类型全部一致才沿用、否则清空；
 * 新段落在**文档序最前那份**选中段的位置。少于两份或下标全部越界时原样返回。
 */
export function mergeSegsIntoOne(d: DraftState, sis: number[]): DraftState {
  const idx = [...new Set(sis)].filter((i) => Number.isInteger(i) && i >= 0 && i < d.segs.length).sort((a, b) => a - b)
  if (idx.length < 2) return d
  const picked = new Set(idx)
  // 页序按文档扁平序：跨段选择（第 1 份 + 第 3 份）合并后页仍是升序
  const flat = flatRefs(d)
  const order = new Map(flat.map((f, i) => [`${f.ref.mi}:${f.ref.p}`, i] as const))
  const refs = d.segs
    .filter((_, i) => picked.has(i))
    .flatMap((sg) => sg.refs)
    .sort((a, b) => (order.get(`${a.mi}:${a.p}`) ?? 0) - (order.get(`${b.mi}:${b.p}`) ?? 0))
  // 类型功能已移除：合并后的新段不再继承/推断 `t`。老草稿里残留的 `t` 只在
  // 头/尾残段上原样带过去（见上面 splitOut），不做任何新赋值。
  // 正文按合并后的页序从各段取（跨源时页号会重复，必须按段分开取），锚不到页就整份按段序拼接
  const pickedSegs = idx.map((i) => d.segs[i]!)
  const parts: MdPart[] = pickedSegs.map((sg) => {
    const own = new Set(sg.refs.map((r) => `${r.mi}:${r.p}`))
    return { seg: sg, pages: refs.filter((r) => own.has(`${r.mi}:${r.p}`)) }
  })
  const slice = joinMdByPages(parts, keepsFirstPage(parts[0]!.seg, refs))
  const merged: Segment = {
    id: nextSegId(),
    t: '',
    fn: defaultSegName(d, refs, false),
    refs,
    manual: true,
    md: slice ? slice.md || undefined : joinWholeMd(pickedSegs),
    pageSpans: slice?.pageSpans.length ? slice.pageSpans : undefined,
    blocks: pickedSegs.reduce<PositionedBlock[] | undefined>((acc, sg) => concatBlocks(acc, sg.blocks), undefined),
  }
  // 新段插在文档序最前那份选中段的位置；其余选中段移除
  const segs: Segment[] = []
  const hadMd = pickedSegs.some((sg) => sg.md)
  d.segs.forEach((sg, i) => {
    if (i === idx[0]) segs.push(markMdMoved(merged, hadMd))
    if (!picked.has(i)) segs.push(sg)
  })
  return withDefaultNames({ ...d, segs })
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
  let changed = false
  const segs = d.segs
    .map((sg) => {
      const refs = sg.refs.filter((r) => !gone.has(`${r.mi}:${r.p}`))
      if (refs.length === sg.refs.length) return sg
      changed = true
      return { ...sg, refs }
    })
    .filter((sg) => sg.refs.length > 0)
  if (!changed) return d
  // 删掉首页后「源名-P起始页」里的起始页变了，默认名跟着刷新
  return withDefaultNames({ ...d, segs })
}
