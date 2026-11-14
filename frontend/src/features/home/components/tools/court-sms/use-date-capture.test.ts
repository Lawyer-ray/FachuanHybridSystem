/**
 * 法院短信 → 记一笔旁线编排的纯逻辑单测（node 环境）。
 *
 * 这里只测可单测的部分：summarize 的汇总语义。轮询编排本身由
 * CourtSmsFlowDialog 的 dom 测试覆盖（需要真实 React 周期）。
 */
import { describe, expect, it } from 'vitest'

import { summarize, type CaptureTask } from './use-date-capture'

function task(over: Partial<CaptureTask> = {}): CaptureTask {
  return {
    task_id: 1,
    document_path: '/tmp/a.pdf',
    document_name: 'a.pdf',
    status: 'success',
    error_message: '',
    classification_hint: '',
    document_type: 'other',
    case_number: '',
    candidate_count: 0,
    pending_count: 0,
    confirmed_count: 0,
    skipped_count: 0,
    date_confirmation_status: 'none',
    ...over,
  }
}

describe('summarize', () => {
  it('识别中：任一任务 pending/processing 即为 running', () => {
    expect(summarize([task({ status: 'pending' })]).running).toBe(true)
    expect(summarize([task({ status: 'processing' })]).running).toBe(true)
    expect(summarize([task({ status: 'success' }), task({ status: 'failed' })]).running).toBe(false)
  })

  it('待确认 / 已确认按任务累加', () => {
    const s = summarize([
      task({ pending_count: 2, confirmed_count: 1 }),
      task({ task_id: 2, pending_count: 3, confirmed_count: 0 }),
    ])
    expect(s.pendingCount).toBe(5)
    expect(s.confirmedCount).toBe(1)
    expect(s.running).toBe(false)
  })

  it('识别为空（0 候选）不计入待确认，也不算 running', () => {
    const s = summarize([task({ candidate_count: 0, pending_count: 0 })])
    expect(s).toEqual({ running: false, pendingCount: 0, confirmedCount: 0 })
  })

  it('空任务列表是安全的（局部返回 / 首屏）', () => {
    expect(summarize([])).toEqual({ running: false, pendingCount: 0, confirmedCount: 0 })
  })
})
