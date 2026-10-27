// @vitest-environment jsdom
/**
 * useCandidateRows 单测（jsdom）。
 *
 * 核心契约：**用户编辑永远赢**。
 * 行内改的 dueLocal / reminderType 不能被 refresh 拉到的新任务快照静默回滚——
 * 这正是旧实现的 bug：候选签名一变 base 行就从服务端重建，同时 overrides 被清空，
 * 律师刚改的时间/类型在绑定案件或跳过一条之后整段消失。
 *
 * 用 renderHook + 一个渲染 rows 的探针组件模拟真实消费方（RecognizeDialog：
 * 编辑经 setOverrides 写入，行由 rows 驱动）。
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { CandidateRow } from '../domain'
import type { TaskOut } from '../types'

import { useCandidateRows } from './use-candidate-rows'

function makeTask(partial: Partial<TaskOut> = {}): TaskOut {
  return {
    task_id: 7,
    status: 'success',
    file_path: null,
    file_url: null,
    recognition: null,
    binding: null,
    date_candidates: [
      {
        id: 1,
        due_at: '2026-10-01T09:00:00',
        reminder_type: 'hearing',
        reminder_type_label: '开庭',
        context_text: '定于……开庭',
        source: 'llm',
        confidence: 0.9,
        status: 'pending',
        reminder_id: null,
      },
    ],
    contacts: [],
    address: null,
    recommendations: [],
    binding_mode: 'standalone',
    date_confirmation_status: 'pending',
    error_message: null,
    created_at: '2026-09-01T10:00:00',
    finished_at: null,
    ...partial,
  } as TaskOut
}

/** 与 DateCandidateList 的 onPatch 同构：按 key 合并局部补丁 */
function patch(
  set: (fn: (prev: Record<string, Partial<CandidateRow>>) => Record<string, Partial<CandidateRow>>) => void,
  key: string,
  patchObj: Partial<CandidateRow>,
) {
  set((prev) => ({ ...prev, [key]: { ...(prev[key] ?? {}), ...patchObj } }))
}

describe('useCandidateRows', () => {
  it('行内改 dueLocal / reminderType 后刷新任务，编辑仍在', async () => {
    const first = makeTask()
    const { result, rerender } = renderHook(
      ({ task }: { task: TaskOut | null }) => useCandidateRows(true, task, undefined),
      { initialProps: { task: first as TaskOut | null } },
    )

    const key = result.current.rows[0]!.key
    act(() => {
      patch(result.current.setOverrides, key, { dueLocal: '2026-12-31T10:30', reminderType: 'appeal_deadline' })
    })
    expect(result.current.rows[0]?.dueLocal).toBe('2026-12-31T10:30')
    expect(result.current.rows[0]?.reminderType).toBe('appeal_deadline')

    // refresh：新任务快照的候选签名变了（另一条被跳过），服务端值仍是旧的
    const refreshed = makeTask({
      date_candidates: [
        { ...makeTask().date_candidates[0]!, status: 'pending' },
        {
          id: 2,
          due_at: '2026-11-01T09:00:00',
          reminder_type: 'other',
          reminder_type_label: '其他',
          context_text: '',
          source: 'regex',
          confidence: 0.3,
          status: 'skipped',
          reminder_id: null,
        },
      ] as TaskOut['date_candidates'],
    })
    rerender({ task: refreshed })

    await waitFor(() => expect(result.current.rows).toHaveLength(2))
    expect(result.current.rows[0]?.dueLocal).toBe('2026-12-31T10:30')
    expect(result.current.rows[0]?.reminderType).toBe('appeal_deadline')
  })

  it('服务端已吸收该编辑时不再继续压着（overrides 收回）', async () => {
    const first = makeTask()
    const { result, rerender } = renderHook(
      ({ task }: { task: TaskOut | null }) => useCandidateRows(true, task, undefined),
      { initialProps: { task: first as TaskOut | null } },
    )
    const key = result.current.rows[0]!.key
    act(() => {
      patch(result.current.setOverrides, key, { reminderType: 'payment_deadline' })
    })

    // 服务端把该候选落库成律师选的值：新快照自带同样的值
    const absorbed = makeTask({
      date_candidates: [
        { ...makeTask().date_candidates[0]!, reminder_type: 'payment_deadline' },
      ] as TaskOut['date_candidates'],
    })
    rerender({ task: absorbed })

    // 服务端已吸收：再换一次快照（只改绑定）不应把值弹回去，也不该再压着旧编辑
    await waitFor(() => expect(result.current.rows[0]?.reminderType).toBe('payment_deadline'))
    rerender({ task: makeTask({ binding: { success: true } as never, date_candidates: absorbed.date_candidates }) })
    await waitFor(() => expect(result.current.rows[0]?.reminderType).toBe('payment_deadline'))
  })

  it('同签名的新 task（如只改了绑定）也让基行更新', async () => {
    const first = makeTask()
    const { result, rerender } = renderHook(
      ({ task }: { task: TaskOut | null }) => useCandidateRows(true, task, undefined),
      { initialProps: { task: first as TaskOut | null } },
    )
    // 候选 id/status 未变 → 签名相同；但服务端把 due_at 规范化了
    const normalized = makeTask({
      date_candidates: [
        { ...makeTask().date_candidates[0]!, due_at: '2026-10-01T09:30:00' },
      ] as TaskOut['date_candidates'],
    })
    rerender({ task: normalized })
    await waitFor(() => expect(result.current.rows[0]?.dueLocal).toBe('2026-10-01T09:30'))
  })

  it('文字路径：候选换一批时新候选用服务端值；用户动过的列按用户值带上', async () => {
    const textRows = (content: string): CandidateRow[] => [
      {
        key: 't-0',
        candidateId: null,
        checked: true,
        dueLocal: '2026-10-01T09:00',
        reminderType: 'hearing',
        label: '开庭',
        contextText: '',
        content,
        source: 'text',
        confidence: null,
        status: 'pending',
        reminderId: null,
      },
    ]
    const { result, rerender } = renderHook(
      ({ rows }: { rows: CandidateRow[] }) => useCandidateRows(false, null, rows),
      { initialProps: { rows: textRows('旧候选') } },
    )
    act(() => {
      patch(result.current.setOverrides, 't-0', { dueLocal: '2026-12-01T08:00' })
    })
    expect(result.current.rows[0]?.dueLocal).toBe('2026-12-01T08:00')

    rerender({ rows: textRows('新候选') })
    await waitFor(() => expect(result.current.rows[0]?.content).toBe('新候选'))
    expect(result.current.rows[0]?.dueLocal).toBe('2026-12-01T08:00')
  })

  it('文字路径：调用方换了同 key 的行对象时，用户勾选仍生效', async () => {
    const row = (content: string): CandidateRow => ({
      key: 't-0',
      candidateId: null,
      checked: true,
      dueLocal: '2026-10-01T09:00',
      reminderType: 'hearing',
      label: '开庭',
      contextText: '',
      content,
      source: 'text',
      confidence: null,
      status: 'pending',
      reminderId: null,
    })
    const { result, rerender } = renderHook(
      ({ rows }: { rows: CandidateRow[] }) => useCandidateRows(false, null, rows),
      { initialProps: { rows: [row('旧候选')] } },
    )
    act(() => {
      patch((fn) => result.current.setOverrides(fn), 't-0', { checked: false })
    })
    expect(result.current.rows[0]?.checked).toBe(false)

    rerender({ rows: [row('新候选')] })
    await waitFor(() => expect(result.current.rows[0]?.content).toBe('新候选'))
    expect(result.current.rows[0]?.checked).toBe(false)
  })
})
