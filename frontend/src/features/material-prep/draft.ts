import { detectMaterialKind, loadPdfDocument } from '@/lib/pdf'
import { fetchAttachmentBytes } from './api'
import type { AttachmentMeta, BundleMat, DraftState, InboxMessageDetail, InfoField, PageKey, Segment } from './types'

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
