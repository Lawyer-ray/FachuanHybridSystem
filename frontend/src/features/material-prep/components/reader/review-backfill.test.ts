/**
 * 复核原因回填的纯逻辑单测。
 *
 * 这一层只有三件事，每件都曾以「白跑一次请求 / 悄悄改坏草稿」的形态出过问题：
 * 1. 什么时候该请求（只补缺、只补非 normal、按任务号去重）
 * 2. 后端返回里哪些条目可用（没有 pk 的、两个字段都空的，一律不进表）
 * 3. 怎么并（**只填空、不覆盖**；无变化要能说出来）
 */
import { describe, expect, it } from 'vitest'

import type { Segment } from '../../types'
import { applyReviewReasons, jobIdsNeedingReviewReason, reviewReasonBySegmentPk } from './review-backfill'

function seg(over: Partial<Segment> & { pk?: number; jobId?: string } = {}): Segment {
  const { pk, jobId, ...rest } = over
  return {
    id: `s-${pk ?? 0}`,
    t: '其他',
    fn: '材料',
    refs: [{ mi: 0, p: 1 }],
    manual: false,
    ...(pk !== undefined && jobId ? { splitRef: { pk, jobId } } : {}),
    ...rest,
  } as Segment
}

describe('jobIdsNeedingReviewReason：该不该请求', () => {
  it('低置信度 + 有后端出处 + 缺原因 → 取它的任务号（同任务只取一次）', () => {
    const segs = [
      seg({ pk: 1, jobId: 'job-a', reviewFlag: 'low_confidence' }),
      seg({ pk: 2, jobId: 'job-a', reviewFlag: 'unrecognized' }),
      seg({ pk: 3, jobId: 'job-b', reviewFlag: 'low_confidence' }),
    ]
    expect(jobIdsNeedingReviewReason(segs)).toEqual(['job-a', 'job-b'])
  })

  it('已经有 sourceMethod 的不再请求（回填过就别重复打后端）', () => {
    expect(jobIdsNeedingReviewReason([seg({ pk: 1, jobId: 'job-a', reviewFlag: 'low_confidence', sourceMethod: 'llm' })]))
      .toEqual([])
  })

  it('正常段、人工拆分段（没有 splitRef）都不请求', () => {
    expect(
      jobIdsNeedingReviewReason([
        seg({ pk: 1, jobId: 'job-a', reviewFlag: 'normal' }),
        seg({ reviewFlag: 'low_confidence' }),
        seg({}),
      ]),
    ).toEqual([])
  })
})

describe('reviewReasonBySegmentPk：哪些条目可用', () => {
  it('按后端主键建表；两个字段都空的（比字段更老的任务）不进表', () => {
    const map = reviewReasonBySegmentPk([
      { id: 11, source_method: 'layout_title', review_flag_label: '低置信度' },
      { id: 12, source_method: '', review_flag_label: '' },
      { source_method: 'llm', review_flag_label: '低置信度' },
    ])
    expect([...map.keys()]).toEqual([11])
    expect(map.get(11)).toEqual({ sourceMethod: 'layout_title', reviewFlagLabel: '低置信度' })
  })
})

describe('applyReviewReasons：只填空、不覆盖', () => {
  const reasons = new Map([
    [11, { sourceMethod: 'layout_title', reviewFlagLabel: '低置信度' }],
    [12, { sourceMethod: 'llm', reviewFlagLabel: '低置信度' }],
  ])

  it('按 splitRef.pk 对上号（不是按数组下标——切/并段后下标会漂移）', () => {
    const segs = [seg({ pk: 12, jobId: 'job-a', reviewFlag: 'low_confidence' }), seg({ pk: 11, jobId: 'job-a', reviewFlag: 'low_confidence' })]
    const next = applyReviewReasons(segs, reasons)!
    expect(next[0]!.sourceMethod).toBe('llm')
    expect(next[1]!.sourceMethod).toBe('layout_title')
  })

  it('已有的值不被覆盖（只有缺的那个字段被补上）', () => {
    const segs = [
      seg({ pk: 11, jobId: 'job-a', reviewFlag: 'low_confidence', sourceMethod: 'rule_weak_only', reviewFlagLabel: '低置信度' }),
    ]
    expect(applyReviewReasons(segs, reasons)).toBeNull()
  })

  it('只缺中文标签时也只补标签，不动已经有的原因', () => {
    const segs = [seg({ pk: 11, jobId: 'job-a', reviewFlag: 'low_confidence', sourceMethod: 'rule_weak_only' })]
    const next = applyReviewReasons(segs, reasons)!
    expect(next[0]!.sourceMethod).toBe('rule_weak_only')
    expect(next[0]!.reviewFlagLabel).toBe('低置信度')
  })

  it('没有变化时返回 null（调用方据此跳过草稿写入）', () => {
    const segs = [seg({ reviewFlag: 'low_confidence' }), seg({ pk: 99, jobId: 'job-x' })]
    expect(applyReviewReasons(segs, reasons)).toBeNull()
  })

  it('改动的段是新对象，没改的段保持原引用（下游 memo 不被整体打穿）', () => {
    const untouched = seg({ pk: 99, jobId: 'job-x' })
    const next = applyReviewReasons([seg({ pk: 11, jobId: 'job-a' }), untouched], reasons)!
    expect(next[0]).not.toBe(undefined)
    expect(next[1]).toBe(untouched)
  })
})
