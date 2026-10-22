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

const confirmMock = vi.hoisted(() => vi.fn())
const revokeMock = vi.hoisted(() => vi.fn())
vi.mock('../api', () => ({
  confirmDates: (...a: unknown[]) => confirmMock(...a),
  revokeDate: (...a: unknown[]) => revokeMock(...a),
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

// ============ 文件模式 / 跳过 / 撤销（2026-10 覆盖率补测） ============

function fileRow(key: string, over: Partial<CandidateRow> = {}): CandidateRow {
  return {
    key,
    candidateId: 100 + Number(key),
    checked: true,
    dueLocal: '2026-10-20T09:00',
    reminderType: 'hearing',
    confidence: 0.9,
    status: 'pending',
    contextText: '',
    label: key,
    content: key,
    ...over,
  } as CandidateRow
}

describe('useConfirmActions（文件模式）', () => {
  it('全部成功：提示写入条数并刷新', async () => {
    const args = baseArgs({ isFileMode: true, task: { task_id: 9 }, rows: [fileRow('1')] })
    confirmMock.mockResolvedValue({ results: [{ status: 'ok', message: '' }] })
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doConfirm()
    })

    expect(confirmMock).toHaveBeenCalledWith(9, [
      { candidate_id: 101, action: 'confirm', due_at: '2026-10-20T09:00', reminder_type: 'hearing' },
    ])
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('已写入 1 条提醒'))
    expect(args.refresh).toHaveBeenCalled()
    expect(args.onSaved).toHaveBeenCalled()
  })

  it('命中复用：提示里标注复用了既有提醒', async () => {
    const args = baseArgs({ isFileMode: true, task: { task_id: 9 }, rows: [fileRow('1')] })
    confirmMock.mockResolvedValue({
      results: [{ status: 'ok', message: '复用了同时间点的既有提醒，未重复创建' }],
    })
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doConfirm()
    })
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('1 条复用了既有提醒'))
  })

  it('有 error 结果：warning 提示未写入数并带首条原因', async () => {
    const args = baseArgs({ isFileMode: true, task: { task_id: 9 }, rows: [fileRow('1'), fileRow('2')] })
    confirmMock.mockResolvedValue({
      results: [
        { status: 'ok', message: '' },
        { status: 'error', message: '日期格式不对' },
      ],
    })
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doConfirm()
    })
    expect(toast.warning).toHaveBeenCalledWith('1 条未写入：日期格式不对')
  })

  it('error 结果缺 message 时用「未知原因」兜底', async () => {
    const args = baseArgs({ isFileMode: true, task: { task_id: 9 }, rows: [fileRow('1')] })
    confirmMock.mockResolvedValue({ results: [{ status: 'error' }] })
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doConfirm()
    })
    expect(toast.warning).toHaveBeenCalledWith('1 条未写入：未知原因')
  })

  it('results 缺省（后端异常路径）按空处理', async () => {
    const args = baseArgs({ isFileMode: true, task: { task_id: 9 }, rows: [fileRow('1')] })
    confirmMock.mockResolvedValue({})
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doConfirm()
    })
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('已写入 0 条提醒'))
  })

  it('接口抛错：error 提示且 busy 复位', async () => {
    const args = baseArgs({ isFileMode: true, task: { task_id: 9 }, rows: [fileRow('1')] })
    confirmMock.mockRejectedValue(new Error('网关超时'))
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doConfirm()
    })
    expect(toast.error).toHaveBeenCalled()
    expect(result.current.busy).toBe(false)
  })
})

describe('useConfirmActions：跳过', () => {
  it('无 candidateId 时是 no-op', async () => {
    const args = baseArgs({ isFileMode: true, task: { task_id: 9 }, rows: [fileRow('1')] })
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doSkip(fileRow('1', { candidateId: null }))
    })
    expect(confirmMock).not.toHaveBeenCalled()
  })

  it('成功：下发 skip 并刷新', async () => {
    const args = baseArgs({ isFileMode: true, task: { task_id: 9 }, rows: [fileRow('1')] })
    confirmMock.mockResolvedValue({})
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doSkip(fileRow('1'))
    })
    expect(confirmMock).toHaveBeenCalledWith(9, [{ candidate_id: 101, action: 'skip' }])
    expect(args.refresh).toHaveBeenCalled()
  })

  it('失败：error 提示', async () => {
    const args = baseArgs({ isFileMode: true, task: { task_id: 9 }, rows: [fileRow('1')] })
    confirmMock.mockRejectedValue(new Error('拒绝'))
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doSkip(fileRow('1'))
    })
    expect(toast.error).toHaveBeenCalled()
  })
})

describe('useConfirmActions：撤销', () => {
  it('无 candidateId 时是 no-op', async () => {
    const args = baseArgs({ isFileMode: true, task: { task_id: 9 }, rows: [fileRow('1')] })
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doRevoke(fileRow('1', { candidateId: null }))
    })
    expect(revokeMock).not.toHaveBeenCalled()
  })

  it('成功：撤销并提示、刷新、回调', async () => {
    const args = baseArgs({ isFileMode: true, task: { task_id: 9 }, rows: [fileRow('1')] })
    revokeMock.mockResolvedValue({})
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doRevoke(fileRow('1'))
    })
    expect(revokeMock).toHaveBeenCalledWith(9, 101)
    expect(toast.success).toHaveBeenCalledWith('已撤销并删除该条提醒')
    expect(args.refresh).toHaveBeenCalled()
    expect(args.onSaved).toHaveBeenCalled()
  })

  it('失败：error 提示', async () => {
    const args = baseArgs({ isFileMode: true, task: { task_id: 9 }, rows: [fileRow('1')] })
    revokeMock.mockRejectedValue(new Error('已删除'))
    const { result } = renderHook(() => useConfirmActions(args as never))

    await act(async () => {
      await result.current.doRevoke(fileRow('1'))
    })
    expect(toast.error).toHaveBeenCalled()
  })
})
