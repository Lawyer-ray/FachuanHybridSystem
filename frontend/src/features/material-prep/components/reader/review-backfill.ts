import type { Segment } from '../../types'

/**
 * 老草稿的「复核原因」回填。
 *
 * ## 为什么需要回填
 *
 * 右栏复核提示条要说清「为什么这一段要复核」，原因来自后端每段的 `source_method`
 * （版面标题猜的起点 / 只命中弱规则 / 和上一段只隔一页……）。但在这之前前端**根本
 * 没有映射这个字段**，所以已经存在浏览器 / 服务端的草稿里只有 `reviewFlag` 和
 * `confidence`——律师打开手里这份 40 段卷宗，只能看到「置信度 62%」，看不到原因。
 *
 * 重跑一次识别能补上，但那是几分钟 + 几十元，只为了一个提示字段，不值。
 * 而 `GET /pdf-splitting/jobs/{job_id}` 的响应本来就带着每段的 `source_method`，
 * 按 `splitRef.pk` 回填即可——一次 GET，零成本。
 *
 * ## 边界
 *
 * - 只在「确实非 normal + 确实缺 sourceMethod」时才请求；回填过就不再请求
 * - 后端也没有（比字段更老的任务）就什么都不改：宁可只显示置信度，也不编原因
 */

/** 需要回填原因的拆分任务号（去重）。空数组 = 这一份草稿没有要补的 */
export function jobIdsNeedingReviewReason(segs: Segment[]): string[] {
  const ids = new Set<string>()
  for (const seg of segs) {
    if (!seg.splitRef) continue
    if (!seg.reviewFlag || seg.reviewFlag === 'normal') continue
    if (seg.sourceMethod) continue
    ids.add(seg.splitRef.jobId)
  }
  return [...ids]
}

/** 后端每段的分段来源（只取回填要用的两个字段） */
export interface ReviewReason {
  sourceMethod: string
  reviewFlagLabel: string
}

/** 后端返回的段列表 → `pk → 原因`。两个字段都空的不进表（免得白发一次草稿更新） */
export function reviewReasonBySegmentPk(
  segments: { id?: number; source_method?: string; review_flag_label?: string }[],
): Map<number, ReviewReason> {
  const map = new Map<number, ReviewReason>()
  for (const item of segments) {
    if (typeof item.id !== 'number') continue
    const sourceMethod = typeof item.source_method === 'string' ? item.source_method : ''
    const reviewFlagLabel = typeof item.review_flag_label === 'string' ? item.review_flag_label : ''
    if (!sourceMethod && !reviewFlagLabel) continue
    map.set(item.id, { sourceMethod, reviewFlagLabel })
  }
  return map
}

/**
 * 把原因并进段列表。**返回 null 表示没有任何变化**（调用方据此跳过草稿写入：
 * 每次打开都写一次草稿会平白制造「有未保存改动」的噪声）。
 */
export function applyReviewReasons(segs: Segment[], reasons: Map<number, ReviewReason>): Segment[] | null {
  let changed = false
  const next = segs.map((seg) => {
    const pk = seg.splitRef?.pk
    if (typeof pk !== 'number') return seg
    const reason = reasons.get(pk)
    if (!reason) return seg
    // **只填空、不覆盖**：草稿里已有的值（可能是律师后来重跑 / 手工改过的）优先。
    // 写反了就是「回填把现有数据冲掉」，而这条路是每次打开阅读器都会走的。
    const sourceMethod = seg.sourceMethod || reason.sourceMethod
    const reviewFlagLabel = seg.reviewFlagLabel || reason.reviewFlagLabel
    if (sourceMethod === seg.sourceMethod && reviewFlagLabel === seg.reviewFlagLabel) return seg
    changed = true
    return { ...seg, sourceMethod, reviewFlagLabel }
  })
  return changed ? next : null
}
