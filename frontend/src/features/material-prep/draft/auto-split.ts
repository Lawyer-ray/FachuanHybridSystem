import type { DraftState, PageKey, PdfSplitSegmentSuggestion, Segment } from '../types'
import { nextSegId } from './seg-id'

/**
 * 云端 PDF 自动拆分 + 源素材改名。
 */

/** 后端对「未识别」的通用标签不算类型；LLM 的开放命名（借条 / 转账凭证等，
 *  类型仍为 unrecognized）经 segment_label 透出，照常作为类型胶囊展示。 */
function suggestedType(item: PdfSplitSegmentSuggestion): string {
  return item.segment_label === '未识别材料' ? '' : item.segment_label
}

/**
 * 把一份拆分建议落成该源上的完整段列表；建议没整覆盖全部页（有洞 / 非法页码）时返回 null。
 *
 * 是 `applyAutoSplit` / `applyAutoSplitPreservingEdits` 的共用前半段：两者只在
 * 「怎么处理人工改过的旧段」上分叉，建段与覆盖校验必须逐字一致。
 */
function buildProposedSegments(
  mi: number,
  pages: number,
  suggestions: PdfSplitSegmentSuggestion[],
): Segment[] | null {
  const proposed: Segment[] = suggestions
    .filter((item) => item.page_start >= 1 && item.page_end >= item.page_start && item.page_end <= pages)
    .map((item) => {
      const refs: PageKey[] = []
      for (let p = item.page_start; p <= item.page_end; p++) refs.push({ mi, p })
      return {
        id: nextSegId(),
        t: suggestedType(item),
        fn: item.filename.replace(/\.pdf$/i, ''),
        refs,
        manual: false,
        reviewFlag: item.review_flag,
        confidence: item.confidence,
        md: item.content_md || undefined,
        // 原文坐标索引：后端已归一化为 0–1 矩形，直接用于页卡上的绿框
        blocks: item.positioned?.length ? item.positioned : undefined,
      }
    })
  const covered = new Set(proposed.flatMap((seg) => seg.refs.map((ref) => ref.p)))
  if (covered.size !== pages || Array.from({ length: pages }, (_, i) => i + 1).some((p) => !covered.has(p))) {
    return null
  }
  return proposed
}

/** 用 proposed 换掉该源上的全部旧段，并按「源序 + 页序」重排 */
function replaceMatSegments(d: DraftState, mi: number, proposed: Segment[]): DraftState {
  const segs = d.segs.filter((seg) => !seg.refs.every((ref) => ref.mi === mi))
  segs.push(...proposed)
  segs.sort((a, b) => {
    const pageA = Math.min(...a.refs.map((ref) => ref.mi * 1_000_000 + ref.p))
    const pageB = Math.min(...b.refs.map((ref) => ref.mi * 1_000_000 + ref.p))
    return pageA - pageB
  })
  return { ...d, segs }
}

/**
 * 应用单个 PDF 的云端拆分建议；只替换该源上未人工编辑的完整分段。
 *
 * 何时用：已经确认可以覆盖（无 manual 段、无跨源合并）的常规路径。
 * 该源上有人工动过正文 / 段名 / 类型时，先问 `detectAutoSplitConflicts`，
 * 需要保留人工内容就用 `applyAutoSplitPreservingEdits` 而不是这个。
 */
export function applyAutoSplit(
  d: DraftState,
  mi: number,
  suggestions: PdfSplitSegmentSuggestion[],
): DraftState {
  const mat = d.mats[mi]
  if (!mat || mat.k !== 'pdf' || suggestions.length === 0) return d
  const existing = d.segs.filter((seg) => seg.refs.some((ref) => ref.mi === mi))
  if (existing.some((seg) => seg.manual || seg.refs.some((ref) => ref.mi !== mi))) return d

  const proposed = buildProposedSegments(mi, mat.pages, suggestions)
  if (!proposed) return d
  return replaceMatSegments(d, mi, proposed)
}

/** 会被 AI 结果替换掉的人工改动清单 */
export interface AutoSplitConflict {
  mi: number
  /** 会被 AI 结果替换掉的人工修改 */
  edited: Array<{ si: number; name: string; what: ('md' | 'name' | 'type')[] }>
}

/**
 * 查这次自动识别会抹掉哪些人工改动——用于**重跑前弹窗询问**。
 *
 * 何时用：拿到拆分建议、真正落草稿之前。返回 null 表示可以放心调
 * `applyAutoSplit`（没有会被替换的人工改动，或该源根本不允许自动拆分）；
 * 返回非 null 时让律师选「保留我的改动」→ `applyAutoSplitPreservingEdits`，
 * 或「用识别结果覆盖」→ `applyAutoSplit`（该源无 manual 段时才走得通）。
 *
 * 判定口径与 `applyAutoSplit` 一致：`canAutoSplitMat` 为假时它整份不应用，
 * 也就不存在冲突。
 */
export function detectAutoSplitConflicts(
  d: DraftState,
  mi: number,
  suggestions: PdfSplitSegmentSuggestion[],
): AutoSplitConflict | null {
  const mat = d.mats[mi]
  if (!mat || mat.k !== 'pdf' || suggestions.length === 0) return null
  if (!canAutoSplitMat(d, mi)) return null

  const edited: AutoSplitConflict['edited'] = []
  d.segs.forEach((seg, si) => {
    if (!seg.refs.some((ref) => ref.mi === mi)) return
    const what = (['md', 'name', 'type'] as const).filter((k) => seg.manualEdit?.[k])
    if (what.length > 0) edited.push({ si, name: seg.fn, what: [...what] })
  })
  return edited.length > 0 ? { mi, edited } : null
}

/**
 * 同 `applyAutoSplit`，但把人工改过的正文搬回新分段上——**重跑识别时默认选这个**。
 *
 * 场景：客户第一次传的扫描件模糊，律师改完正文后又让客户重传了清晰版；或隔几天
 * 重跑一次识别。人改过的东西不能被静默抹掉。
 *
 * 搬法：按页范围重叠匹配——新段覆盖了旧段的哪些页，就把旧 md 搬给重叠页数最多的
 * 新段，一个旧段只搬一次（多新段都重叠时取重叠最多者，并列取页序靠前的）。
 * 想不清楚时宁可保留旧 md：md 丢了比留着错更难接受。
 *
 * 只保 md：段名 / 类型仍用识别结果——改过名的段，识别给出的新命名往往更准，
 * 而正文里是律师逐字核过的内容。段名冲突由 `detectAutoSplitConflicts` 报给 UI。
 */
export function applyAutoSplitPreservingEdits(
  d: DraftState,
  mi: number,
  suggestions: PdfSplitSegmentSuggestion[],
): DraftState {
  const mat = d.mats[mi]
  if (!mat || mat.k !== 'pdf' || suggestions.length === 0) return d
  const existing = d.segs.filter((seg) => seg.refs.some((ref) => ref.mi === mi))
  if (existing.some((seg) => seg.manual || seg.refs.some((ref) => ref.mi !== mi))) return d

  const proposed = buildProposedSegments(mi, mat.pages, suggestions)
  if (!proposed) return d

  const oldMd = existing.filter((seg) => seg.manualEdit?.md && seg.md)
  for (const old of oldMd) {
    const oldPages = new Set(old.refs.filter((ref) => ref.mi === mi).map((ref) => ref.p))
    let best: Segment | undefined
    let bestOverlap = 0
    for (const seg of proposed) {
      const overlap = seg.refs.filter((ref) => oldPages.has(ref.p)).length
      if (overlap > bestOverlap) {
        best = seg
        bestOverlap = overlap
      }
    }
    if (best) best.md = old.md
  }

  return replaceMatSegments(d, mi, proposed)
}

/** 有人工拆分或跨源合并时，避免自动识别覆盖这些操作。 */
export function canAutoSplitMat(d: DraftState, mi: number): boolean {
  return !d.segs.some(
    (seg) => seg.refs.some((ref) => ref.mi === mi) && (seg.manual || seg.refs.some((ref) => ref.mi !== mi)),
  )
}

/** 源素材改名（同步沿用的默认段名）；改回源文件名 = 清除自定义名 */
export function renameMat(d: DraftState, mi: number, n: string): DraftState {
  const name = n.trim()
  const cur = d.mats[mi]
  if (!name || !cur || cur.customName === name) return d
  // 改名前的显示名：改回源文件名时要靠它把跟随的段名一并改回去
  const oldName = cur.customName || cur.n
  const mats = d.mats.map((m, i) =>
    i === mi ? { ...m, customName: name !== m.n ? name : undefined } : m
  )
  // 只改仍跟随该源文件显示名（未被单独改过）的段
  const segs = d.segs.map((sg) =>
    sg.fn === oldName && sg.refs.length > 0 && sg.refs.every((r) => r.mi === mi)
      ? { ...sg, fn: name }
      : sg
  )
  return { ...d, mats, segs }
}
