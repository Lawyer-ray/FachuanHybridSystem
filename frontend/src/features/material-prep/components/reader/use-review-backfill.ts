import { useEffect, useRef } from 'react'

import { getPdfSplitJob } from '../../api'
import type { DraftState } from '../../types'
import { applyReviewReasons, jobIdsNeedingReviewReason, reviewReasonBySegmentPk } from './review-backfill'

/**
 * 打开阅读器时，把老草稿里缺的「复核原因」从后端回填一次（见 `review-backfill.ts`）。
 *
 * 三条纪律，每条都对应一次踩过的坑：
 *
 * 1. **只补缺、不覆盖**：`applyReviewReasons` 只在字段为空时写入，律师/后端已有的值
 *    一律不动——回填是补数据，不是「以服务端为准重写草稿」。
 * 2. **每个任务号只试一次**：比 `source_method` 更老的后端任务回不来这个字段，
 *    没有这个闸门就会每次渲染发一次 GET、永远重试。
 * 3. **失败静默**：回填只影响提示条的详细程度，失败时右栏照常显示「置信度 62%」。
 *    为一个提示字段弹 toast 或拖垮阅读器，比没有它更糟。
 *
 * 「待补的任务号」在 effect 里算而不是渲染期算：`tried` 是 ref，渲染期读它会被
 * `react-hooks/refs` 判为「在 render 里读可变值」（React Compiler 下更危险）。
 */
export function useReviewBackfill(
  draft: DraftState | null,
  update: (fn: (d: DraftState) => DraftState) => void,
) {
  const tried = useRef<Set<string>>(new Set())

  useEffect(() => {
    if (!draft) return
    const jobIds = jobIdsNeedingReviewReason(draft.segs).filter((id) => !tried.current.has(id))
    if (jobIds.length === 0) return
    for (const jobId of jobIds) tried.current.add(jobId)

    let cancelled = false
    void Promise.all(
      jobIds.map(async (jobId) => {
        try {
          const job = await getPdfSplitJob(jobId)
          if (cancelled) return
          const reasons = reviewReasonBySegmentPk(job.segments ?? [])
          if (reasons.size === 0) return
          update((d) => {
            const segs = applyReviewReasons(d.segs, reasons)
            return segs ? { ...d, segs } : d
          })
        } catch {
          // 见文件头第 3 条：静默
        }
      }),
    )

    return () => {
      cancelled = true
    }
  }, [draft, update])
}
