import { detectMaterialKind, loadPdfDocument } from '@/lib/pdf'
import { fetchAttachmentBytes } from './api'
import { SEG_COLORS } from './constants'
import type {
  AssignInfo,
  AttachmentMeta,
  BundleMat,
  DraftState,
  InboxMessageDetail,
  InfoField,
  PageKey,
  PdfSplitSegmentSuggestion,
  PackStatus,
  Segment,
} from './types'

/** 每个附件算出一个源素材，并解析真实页数（PDF 需要载入文档取页数）。 */
export async function resolveMats(msg: InboxMessageDetail): Promise<BundleMat[]> {
  const mats: BundleMat[] = []
  for (const att of msg.attachments) {
    const n = effectiveFileName(att)
    const k = detectMaterialKind(att.content_type, n)
    let pages = 1
    if (k === 'pdf') {
      try {
        const bytes = await fetchAttachmentBytes(msg.id, att.part_index)
        const doc = await loadPdfDocument(`${msg.id}:${att.part_index}`, bytes)
        pages = doc.numPages
      } catch {
        pages = 1
      }
    }
    mats.push({ partIndex: att.part_index, n, k, pages })
  }
  return mats
}

/** 附件展示名：优先自定义名，其次原始名 */
export function effectiveFileName(att: AttachmentMeta): string {
  return att.custom_filename?.trim() || att.original_filename || att.filename
}

/** 每个源素材默认一整段，覆盖其全部页 */
export function initialSegments(mats: BundleMat[]): Segment[] {
  return mats.map((m, mi) => {
    const refs: PageKey[] = []
    for (let p = 1; p <= m.pages; p++) refs.push({ mi, p })
    return { t: '', fn: m.n, refs, manual: false }
  })
}

/** 初始草稿：每个附件一段，右栏默认只记委托人 + 对方当事人 */
export function buildInitialDraft(_msg: InboxMessageDetail, mats: BundleMat[]): DraftState {
  return {
    mats,
    segs: initialSegments(mats),
    infos: [
      { k: '委托人', v: '', src: '', srcRef: null, ph: '姓名或单位' },
      { k: '对方当事人', v: '', src: '', srcRef: null, ph: '姓名或单位', hint: '多个用、分隔' },
    ],
  }
}

export function matLabel(mats: BundleMat[], mi: number): string {
  return mats[mi]?.customName || mats[mi]?.n || `材料 ${mi + 1}`
}

export function segMats(sg: Segment): number[] {
  return [...new Set(sg.refs.map((r) => r.mi))]
}

export function isCross(sg: Segment): boolean {
  return segMats(sg).length > 1
}

/** 段跨了多少个源（用于左栏「整份」判定与来源标签） */
export function pageLabel(mats: BundleMat[], raw: PageKey): string {
  return `${matLabel(mats, raw.mi)} P${raw.p}`
}

// ---------------------------------------------------------------------------
// 不可变分段运算：所有函数返回新的 DraftState
// ---------------------------------------------------------------------------

/**
 * 在段 si 内部第 k 个页缝处切开（k 为该段 refs 的切分点，0..refs.length-2）。
 * 把该段拆成两段，各自沿用原段的类型（新段类型清空、名取来源名）。
 */
export function splitSegment(d: DraftState, si: number, k: number): DraftState {
  if (si < 0 || si >= d.segs.length) return d
  const cur = d.segs[si]
  if (!cur || cur.refs.length < 2) return d
  if (k < 0 || k >= cur.refs.length - 1) return d
  const head = cur.refs.slice(0, k + 1)
  const tail = cur.refs.slice(k + 1)
  const tailFirst = tail[0]
  const newSeg: Segment = {
    t: '',
    fn: matLabel(d.mats, tailFirst.mi),
    refs: tail,
    manual: true,
  }
  const next = d.segs.map((sg, i) => (i === si ? { ...sg, refs: head, manual: sg.manual || true } : sg))
  next.splice(si + 1, 0, newSeg)
  return { ...d, segs: next }
}

/** 段 si 并入上一段（si>0） */
export function mergeSegment(d: DraftState, si: number): DraftState {
  if (si <= 0 || si >= d.segs.length) return d
  const cur = d.segs[si]
  const next = d.segs.map((sg, i) => {
    if (i === si - 1) return { ...sg, refs: [...sg.refs, ...cur.refs], manual: sg.manual || cur.manual }
    return sg
  })
  next.splice(si, 1)
  return { ...d, segs: next }
}

/** 改段类型 */
export function setSegmentType(d: DraftState, si: number, t: string): DraftState {
  if (si < 0 || si >= d.segs.length || t === d.segs[si].t) return d
  const segs = d.segs.map((sg, i) => (i === si ? { ...sg, t } : sg))
  return { ...d, segs }
}

/** 改段名 */
export function renameSegment(d: DraftState, si: number, fn: string): DraftState {
  if (si < 0 || si >= d.segs.length) return d
  const name = fn.trim()
  if (!name || name === d.segs[si].fn) return d
  const segs = d.segs.map((sg, i) => (i === si ? { ...sg, fn: name } : sg))
  return { ...d, segs }
}

/** 恢复初始分段 */
export function resetSegments(d: DraftState): DraftState {
  return { ...d, segs: initialSegments(d.mats) }
}

/** 应用单个 PDF 的云端拆分建议；只替换该源上未人工编辑的完整分段。 */
export function applyAutoSplit(
  d: DraftState,
  mi: number,
  suggestions: PdfSplitSegmentSuggestion[],
): DraftState {
  const mat = d.mats[mi]
  if (!mat || mat.k !== 'pdf' || suggestions.length === 0) return d
  const existing = d.segs.filter((seg) => seg.refs.some((ref) => ref.mi === mi))
  if (existing.some((seg) => seg.manual || seg.refs.some((ref) => ref.mi !== mi))) return d

  const proposed: Segment[] = suggestions
    .filter((item) => item.page_start >= 1 && item.page_end >= item.page_start && item.page_end <= mat.pages)
    .map((item) => {
      const refs: PageKey[] = []
      for (let p = item.page_start; p <= item.page_end; p++) refs.push({ mi, p })
      return {
        t: item.segment_type === 'unrecognized' ? '' : item.segment_label,
        fn: item.filename.replace(/\.pdf$/i, ''),
        refs,
        manual: false,
        reviewFlag: item.review_flag,
        confidence: item.confidence,
      }
    })
  const covered = new Set(proposed.flatMap((seg) => seg.refs.map((ref) => ref.p)))
  if (covered.size !== mat.pages || Array.from({ length: mat.pages }, (_, i) => i + 1).some((p) => !covered.has(p))) {
    return d
  }

  const segs = d.segs.filter((seg) => !seg.refs.every((ref) => ref.mi === mi))
  segs.push(...proposed)
  segs.sort((a, b) => {
    const pageA = Math.min(...a.refs.map((ref) => ref.mi * 1_000_000 + ref.p))
    const pageB = Math.min(...b.refs.map((ref) => ref.mi * 1_000_000 + ref.p))
    return pageA - pageB
  })
  return { ...d, segs }
}

/** 有人工拆分或跨源合并时，避免自动识别覆盖这些操作。 */
export function canAutoSplitMat(d: DraftState, mi: number): boolean {
  return !d.segs.some(
    (seg) => seg.refs.some((ref) => ref.mi === mi) && (seg.manual || seg.refs.some((ref) => ref.mi !== mi)),
  )
}

/** 源素材改名（同步沿用的默认段名） */
export function renameMat(d: DraftState, mi: number, n: string): DraftState {
  const name = n.trim()
  if (!name || d.mats[mi]?.customName === name || d.mats[mi]?.n === name) return d
  const mats = d.mats.map((m, i) =>
    i === mi ? { ...m, customName: name !== m.n ? name : undefined } : m
  )
  // 只改仍沿用默认名（等于源文件名）的段
  const segs = d.segs.map((sg) =>
    sg.fn === (d.mats[mi]?.n || '') && sg.refs.length > 0 && sg.refs.every((r) => r.mi === mi)
      ? { ...sg, fn: name }
      : sg
  )
  return { ...d, mats, segs }
}

// ---------------------------------------------------------------------------
// 右栏信息便签
// ---------------------------------------------------------------------------

export function addInfoField(d: DraftState, field: InfoField): DraftState {
  if (d.infos.some((f) => f.k === field.k)) return d
  return { ...d, infos: [...d.infos, { ...field }] }
}

export function removeInfoField(d: DraftState, di: number): DraftState {
  if (di < 0 || di >= d.infos.length) return d
  return { ...d, infos: d.infos.filter((_, i) => i !== di) }
}

export function setInfoValue(d: DraftState, di: number, v: string): DraftState {
  if (di < 0 || di >= d.infos.length) return d
  const infos = d.infos.map((f, i) => (i === di ? { ...f, v } : f))
  return { ...d, infos }
}

export function setInfoSource(d: DraftState, di: number, src: string, srcRef: InfoField['srcRef']): DraftState {
  if (di < 0 || di >= d.infos.length) return d
  const infos = d.infos.map((f, i) => (i === di ? { ...f, src, srcRef } : f))
  return { ...d, infos }
}

// ---------------------------------------------------------------------------
// 汇总统计（卡片/清单/进度用）
// ---------------------------------------------------------------------------

export function countUnclassified(d: DraftState): number {
  return d.segs.filter((s) => !s.t).length
}

export function isAllClassified(d: DraftState): boolean {
  return d.segs.length > 0 && d.segs.every((s) => s.t)
}

export function totalPagesOfMats(mats: BundleMat[]): number {
  return mats.reduce((sum, m) => sum + m.pages, 0)
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

// ---------------------------------------------------------------------------
// 选页 → 独立 / 合并
// ---------------------------------------------------------------------------

/** 段色：按段序取色盘，稳定不闪 */
export function segColorOf(si: number): string {
  return SEG_COLORS[si % SEG_COLORS.length]
}

/** 页面唯一键（用于选中集合） */
export const selKeyOf = (r: PageKey): string => `${r.mi}:${r.p}`

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

export function pageKeyOf(mi: number, p: number): string {
  return `${mi}:${p}`
}

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

/** 新段默认名：单源用源文件名当底，跨源用当前段名；带起始页，切第二次不叠后缀 */
function splitBase(sg: Segment, mats: BundleMat[]): string {
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

// ---------------------------------------------------------------------------
// 材料包状态 / 归案信息（持久化到 draft_state）
// ---------------------------------------------------------------------------

export function setPackStatus(d: DraftState, status: PackStatus): DraftState {
  if (d.status === status) return d
  return { ...d, status }
}

export function setPackAssign(d: DraftState, assign: AssignInfo): DraftState {
  return { ...d, assign, status: 'done' }
}

export function appendMatsToDraft(d: DraftState, added: BundleMat[]): DraftState {
  if (!added.length) return d
  const mats = [...d.mats, ...added]
  const segs = [...d.segs]
  added.forEach((m, idx) => {
    const mi = d.mats.length + idx
    const refs: PageKey[] = []
    for (let p = 1; p <= m.pages; p++) refs.push({ mi, p })
    segs.push({ t: '', fn: m.n, refs, manual: false })
  })
  return { ...d, mats, segs }
}
