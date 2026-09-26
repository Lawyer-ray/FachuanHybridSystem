import type { AssignInfo, BundleMat, DraftState, PackStatus, PageKey, Segment } from '../types'
import { matLabel } from './labels'
import { initialSegments } from './resolve'

/**
 * 基础段不可变运算：所有函数返回新的 DraftState。
 */

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
