import type { DraftState, PageKey, PdfSplitSegmentSuggestion, Segment } from '../types'

/**
 * 云端 PDF 自动拆分 + 源素材改名。
 */

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
