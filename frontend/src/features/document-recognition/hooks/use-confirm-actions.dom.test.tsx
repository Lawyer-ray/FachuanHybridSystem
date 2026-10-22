// @vitest-environment jsdom
/**
 * useConfirmActions 文字路径回归测试。
 *
 * 背景（2026-10 审查 D-P2-3 / H-P1-2）：文字路径的 onConfirmText 由 home 注入，
 * 逐条 POST /reminders/create。此前串行 await 中途失败时，前面已建成功的
 * 提醒不会从待处理行里移除，用户重试会重复创建。
 */
import { act, renderHook } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() },
}))

vi.mock('../api', () => ({
  confirmDates: vi.fn(),
}))

import { toast } from 'sonner'

import { useConfirmActions } from './use-confirm-actions'
import type { CandidateRow } from '../domain'

function textRow(key: string, checked = true): CandidateRow {
  return {
    key,
    candidateId: null,
    checked,
    dueLocal: '2026-10-20T09:00',
    reminderType: 'hearing',
    confidence: null,
    status: 'pending',
    contextText: '',
    label: key,
    content: key,
  } as CandidateRow
}

function baseArgs(over: Record<string, unknown> = {}) {
  return {
    isFileMode: false,
    task: undefined,
    rows: [textRow('a'), textRow('b')],
    onSaved: vi.fn(),
    onClose: vi.fn(),
    onConfirmText: vi.fn(async () => 0),
    refresh: vi.fn(async () => {}),
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
})

describe('useConfirmActions（文字路径）', () => {
  it('未勾选时提示且不发请求', async () => {
    const args = baseArgs({ rows: [textRow('a', false)] })
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doConfirm()
    })

    expect(toast.info).toHaveBeenCalledWith('请先勾选要写入的日期')
    expect(args.onConfirmText).not.toHaveBeenCalled()
  })

  it('全部成功：提示条数、关闭弹窗、刷新', async () => {
    const args = baseArgs({ onConfirmText: vi.fn(async () => 2) })
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doConfirm()
    })

    expect(toast.success).toHaveBeenCalledWith('已加入日历 2 条')
    expect(args.onClose).toHaveBeenCalled()
    expect(args.onSaved).toHaveBeenCalled()
  })

  it('部分失败：onConfirmText 抛错时给出错误提示且不复位 busy', async () => {
    const args = baseArgs({
      onConfirmText: vi.fn(async () => {
        throw new Error('第 2 条失败')
      }),
    })
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doConfirm()
    })

    expect(toast.error).toHaveBeenCalled()
    // busy 必须复位，否则用户无法重试
    expect(result.current.busy).toBe(false)
    // 失败时不得关闭弹窗（用户要看到剩余行）
    expect(args.onClose).not.toHaveBeenCalled()
  })

  it('busy 期间重复点击不重复发请求', async () => {
    let release: () => void = () => {}
    const onConfirmText = vi.fn(
      () =>
        new Promise<number>((res) => {
          release = () => res(2)
        }),
    )
    const args = baseArgs({ onConfirmText })
    const { result } = renderHook(() => useConfirmActions(args as never))

    let first: Promise<void>
    act(() => {
      first = result.current.doConfirm()
    })
    await act(async () => {
      await result.current.doConfirm()
    })
    release()
    await act(async () => {
      await first!
    })

    expect(onConfirmText).toHaveBeenCalledTimes(1)
  })
})
