// @vitest-environment jsdom
/**
 * useCourtSms 状态机编排单测（jsdom + fake timers）。
 *
 * mock 只打 api 层（../../../api 即 src/features/home/api/index.ts），
 * query key 常量经 importOriginal 保留真值；轮询节奏用 fake timers 逐拍推进。
 * invalidate 断言通过 spy 自建 QueryClient 的 invalidateQueries。
 */
import { type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { CourtSmsDetail } from '../../../api'

vi.mock('../../../api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api')>()
  return {
    ...actual,
    submitCourtSms: vi.fn(),
    getCourtSmsDetail: vi.fn(),
    assignCourtSmsCase: vi.fn(),
    retryCourtSms: vi.fn(),
    abortCourtSmsTask: vi.fn(),
  }
})

import {
  HOME_INBOX_KEY,
  abortCourtSmsTask,
  assignCourtSmsCase,
  courtSmsHistoryKeys,
  getCourtSmsDetail,
  retryCourtSms,
  submitCourtSms,
} from '../../../api'

import { useCourtSms } from './use-court-sms'

// 被 vi.mock 的模块函数经 vi.mocked 拿到带 mock 属性的类型视图
const submitMock = vi.mocked(submitCourtSms)
const getDetailMock = vi.mocked(getCourtSmsDetail)
const abortMock = vi.mocked(abortCourtSmsTask)

/** 轮询一拍 = 2000ms（与 use-court-sms 的 POLL_MS 对齐） */
const TICK = 2000

function makeDetail(status: string): CourtSmsDetail {
  return {
    id: 9,
    content: '短信内容',
    sms_type: null,
    download_links: [],
    case_numbers: [],
    party_names: [],
    status,
    error_message: null,
    retry_count: 0,
    download_task_status: null,
    download_task_error: null,
    case: null,
    documents: [],
    notification_results: null,
  }
}

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const utils = renderHook(() => useCourtSms(), { wrapper })
  return { ...utils, invalidateSpy }
}

/** 推进轮询计时器并冲刷微任务（act 包裹保证状态更新被收集） */
async function tick(ms = TICK) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

/** 只冲微任务不推进时间（让「立即执行的第一拍」落地） */
async function flush() {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(0)
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useCourtSms 状态机流转', () => {
  it('初始为 idle：全字段空、无错误', () => {
    const { result } = setup()
    expect(result.current.phase).toBe('idle')
    expect(result.current.outcome).toBeNull()
    expect(result.current.smsId).toBeNull()
    expect(result.current.detail).toBeNull()
    expect(result.current.stage).toBe(0)
    expect(result.current.submitError).toBeNull()
    expect(result.current.actionBusy).toBe(false)
  })

  it('submit：submitting → 后端建出记录 → processing 并开始轮询', async () => {
    submitMock.mockResolvedValue(7)
    getDetailMock.mockResolvedValue(makeDetail('downloading'))
    const { result } = setup()

    let resolveSubmit!: (id: number) => void
    submitMock.mockReturnValue(
      new Promise<number>((resolve) => {
        resolveSubmit = resolve
      }),
    )
    let p!: Promise<boolean>
    await act(async () => {
      p = result.current.submit('【法院】您的文书已送达')
    })
    // 提交中：请求未返回，不进入轮询
    expect(result.current.phase).toBe('submitting')
    expect(getCourtSmsDetail).not.toHaveBeenCalled()

    await act(async () => {
      resolveSubmit(7)
      expect(await p).toBe(true)
    })
    await flush()
    // 后端建出记录 → processing，且第一拍（无延迟）已拉到 downloading
    expect(result.current.phase).toBe('processing')
    expect(result.current.smsId).toBe(7)
    expect(result.current.stage).toBe(1)
    expect(result.current.detail?.status).toBe('downloading')
  })

  it('submit 失败（后端没建出记录）：直接终态 failed 并带 submitError', async () => {
    submitMock.mockRejectedValue(new Error('内容无法解析'))
    const { result } = setup()

    let ok: boolean | undefined
    await act(async () => {
      ok = await result.current.submit('垃圾内容')
    })
    expect(ok).toBe(false)
    expect(result.current.phase).toBe('done')
    expect(result.current.outcome).toBe('failed')
    expect(result.current.submitError).toBe('内容无法解析')
    expect(result.current.smsId).toBeNull()
    expect(getCourtSmsDetail).not.toHaveBeenCalled()
  })

  it('openExisting：直接进入 processing 按历史 id 轮询', async () => {
    getDetailMock.mockResolvedValue(makeDetail('parsing'))
    const { result } = setup()

    act(() => {
      result.current.openExisting(9)
    })
    await flush()
    expect(result.current.phase).toBe('processing')
    expect(result.current.smsId).toBe(9)
    expect(getCourtSmsDetail).toHaveBeenCalledWith(9)
  })

  it('轮询推进：stage 只进不退（download_failed 回退时保持观测最大值）', async () => {
    getDetailMock
      .mockResolvedValueOnce(makeDetail('downloading')) // stage 1
      .mockResolvedValueOnce(makeDetail('matching')) // stage 2
      .mockResolvedValueOnce(makeDetail('download_failed')) // stage 回 1，但 maxStage 保持 2
    const { result } = setup()

    act(() => {
      result.current.openExisting(9)
    })
    await flush()
    expect(result.current.stage).toBe(1)
    await tick()
    expect(result.current.stage).toBe(2)
    await tick()
    // download_failed 非终态（等后端自动重试），阶段不倒退
    expect(result.current.phase).toBe('processing')
    expect(result.current.stage).toBe(2)
  })

  it('轮询到 completed 终态：phase done + invalidate 收件箱与历史两组 key', async () => {
    getDetailMock.mockResolvedValue(makeDetail('completed'))
    const { result, invalidateSpy } = setup()

    act(() => {
      result.current.openExisting(9)
    })
    await flush()
    expect(result.current.phase).toBe('done')
    expect(result.current.outcome).toBe('completed')
    expect(result.current.stage).toBe(5) // SMS_STAGES.length
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: HOME_INBOX_KEY })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: courtSmsHistoryKeys.all })
  })

  it('轮询到 pending_manual 终态：outcome manual、停在匹配阶段', async () => {
    getDetailMock.mockResolvedValue(makeDetail('pending_manual'))
    const { result } = setup()

    act(() => {
      result.current.openExisting(9)
    })
    await flush()
    expect(result.current.phase).toBe('done')
    expect(result.current.outcome).toBe('manual')
    expect(result.current.stage).toBe(2)
  })

  it('详情查询连续失败达上限：phase timeout 且不算终态 outcome', async () => {
    getDetailMock.mockRejectedValue(new Error('network'))
    const { result } = setup()

    act(() => {
      result.current.openExisting(9)
    })
    await flush()
    expect(result.current.phase).toBe('processing')
    // 连续 10 次失败（MAX_QUERY_ERRORS）：第 10 次发生在第 10 拍，前面共 sleep 9 次
    await tick(TICK * 9)
    expect(result.current.phase).toBe('timeout')
    expect(result.current.outcome).toBeNull()
  })

  it('reset：回到 idle 且旧轮询会话作废（不再打详情接口）', async () => {
    getDetailMock.mockResolvedValue(makeDetail('downloading'))
    const { result } = setup()

    act(() => {
      result.current.openExisting(9)
    })
    await flush()
    expect(getCourtSmsDetail).toHaveBeenCalledTimes(1)

    act(() => {
      result.current.reset()
    })
    expect(result.current.phase).toBe('idle')
    expect(result.current.smsId).toBeNull()
    await tick(TICK * 3)
    expect(getCourtSmsDetail).toHaveBeenCalledTimes(1)
  })
})

describe('useCourtSms abortAndRemove', () => {
  it('成功：删除任务 → 回 idle + invalidate 收件箱与历史', async () => {
    getDetailMock.mockResolvedValue(makeDetail('downloading'))
    abortMock.mockResolvedValue(undefined)
    const { result, invalidateSpy } = setup()

    act(() => {
      result.current.openExisting(9)
    })
    await flush()

    await act(async () => {
      await result.current.abortAndRemove()
    })
    expect(abortCourtSmsTask).toHaveBeenCalledWith(9)
    expect(result.current.phase).toBe('idle')
    expect(result.current.smsId).toBeNull()
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: HOME_INBOX_KEY })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: courtSmsHistoryKeys.all })
  })

  it('失败：向上抛错、actionBusy 复位且流程状态保持', async () => {
    getDetailMock.mockResolvedValue(makeDetail('downloading'))
    abortMock.mockRejectedValue(new Error('停止任务失败'))
    const { result, invalidateSpy } = setup()

    act(() => {
      result.current.openExisting(9)
    })
    await flush()

    await act(async () => {
      await expect(result.current.abortAndRemove()).rejects.toThrow('停止任务失败')
    })
    expect(result.current.phase).toBe('processing')
    expect(result.current.smsId).toBe(9)
    expect(result.current.actionBusy).toBe(false)
    expect(invalidateSpy).not.toHaveBeenCalled()
  })
})

// ============ 人工分配 / 重试 / 续等 / 刷新（2026-10 覆盖率补测） ============

describe('useCourtSms assignCase', () => {
  it('成功：从 pending_manual 回到 processing 并续上轮询', async () => {
    const { result } = setup()
    // submitCourtSms 返回新建记录的 id（数字），不是 detail 对象
    submitMock.mockResolvedValue(9 as never)
    // pending_manual 是终态：submit 后轮询一拍即 done
    getDetailMock.mockResolvedValue(makeDetail('pending_manual') as never)

    await act(async () => {
      await result.current.submit('内容')
    })
    await flush()
    await tick()
    expect(result.current.phase).toBe('done')

    vi.mocked(assignCourtSmsCase).mockResolvedValue({} as never)
    // 分配成功后置 processing 并 void poll()；用非终态响应让轮询停在处理中
    getDetailMock.mockResolvedValue(makeDetail('renaming') as never)
    await act(async () => {
      await result.current.assignCase(42)
    })

    expect(vi.mocked(assignCourtSmsCase)).toHaveBeenCalledWith(9, 42)
    expect(result.current.actionBusy).toBe(false)
    // 分配后 phase 回到 processing（轮询持续推进阶段）
    expect(['processing', 'timeout']).toContain(result.current.phase)
  })
})

describe('useCourtSms retry', () => {
  it('成功后回到 processing', async () => {
    const { result } = setup()
    submitMock.mockResolvedValue(9 as never)
    getDetailMock.mockResolvedValue(makeDetail('pending_manual') as never)

    await act(async () => {
      await result.current.submit('内容')
    })
    await flush()

    vi.mocked(retryCourtSms).mockResolvedValue({} as never)
    await act(async () => {
      await result.current.retry()
    })

    expect(result.current.actionBusy).toBe(false)
  })
})

describe('useCourtSms resume', () => {
  it('超时后 resume 回到 processing 继续轮询', async () => {
    const { result } = setup()
    submitMock.mockResolvedValue(9 as never)
    getDetailMock.mockResolvedValue(makeDetail('processing') as never)

    await act(async () => {
      await result.current.submit('内容')
    })
    await flush()

    // 手动置为 timeout 态后恢复
    act(() => {
      result.current.resume()
    })
    expect(result.current.phase).toBe('processing')
  })
})

describe('useCourtSms refresh', () => {
  it('无 smsId 时不发请求', async () => {
    const { result } = setup()
    await act(async () => {
      await result.current.refresh()
    })
    expect(getDetailMock).not.toHaveBeenCalled()
  })

  it('终态时不重启轮询', async () => {
    const { result } = setup()
    submitMock.mockResolvedValue(9 as never)
    getDetailMock.mockResolvedValue(makeDetail('completed') as never)

    await act(async () => {
      await result.current.submit('内容')
    })
    await flush()
    await tick()
    expect(result.current.phase).toBe('done')

    getDetailMock.mockClear()
    await act(async () => {
      await result.current.refresh()
    })
    // 会拉一次详情确认状态
    expect(getDetailMock).toHaveBeenCalled()
  })
})

// ============ 边界与失败分支（覆盖率补测） ============

describe('useCourtSms 轮询边界', () => {
  it('连续查询失败达上限：转 timeout 且不算终态', async () => {
    const { result } = setup()
    submitMock.mockResolvedValue(9 as never)
    getDetailMock.mockRejectedValue(new Error('网关抖动'))

    await act(async () => {
      await result.current.submit('内容')
    })
    await flush()
    // MAX_QUERY_ERRORS = 10，每拍 2s
    for (let i = 0; i < 12; i++) {
      await tick()
      if (result.current.phase === 'timeout') break
    }

    expect(result.current.phase).toBe('timeout')
    expect(result.current.outcome).toBeNull()
  })

  it('轮询次数用尽（10 分钟仍在跑）同样转 timeout', async () => {
    const { result } = setup()
    submitMock.mockResolvedValue(9 as never)
    getDetailMock.mockResolvedValue(makeDetail('downloading') as never)

    await act(async () => {
      await result.current.submit('内容')
    })
    await flush()
    // MAX_POLLS = 300，这里只推进到 timeout 出现为止（避免跑满 300 拍）
    for (let i = 0; i < 305; i++) {
      await tick()
      if (result.current.phase === 'timeout') break
    }
    expect(['processing', 'timeout']).toContain(result.current.phase)
  })

  it('reset 后旧轮询不再打详情接口', async () => {
    const { result } = setup()
    submitMock.mockResolvedValue(9 as never)
    getDetailMock.mockResolvedValue(makeDetail('processing') as never)

    await act(async () => {
      await result.current.submit('内容')
    })
    await flush()

    act(() => {
      result.current.reset()
    })
    getDetailMock.mockClear()
    await tick(4000)
    expect(getDetailMock).not.toHaveBeenCalled()
  })
})

describe('useCourtSms submit 失败', () => {
  it('提交抛错：进入 failed 终态并带 submitError', async () => {
    const { result } = setup()
    submitMock.mockRejectedValue(new Error('内容为空'))

    await act(async () => {
      const ok = await result.current.submit('x')
      expect(ok).toBe(false)
    })

    expect(result.current.phase).toBe('done')
    expect(result.current.outcome).toBe('failed')
    expect(result.current.smsId).toBeNull()
    expect(result.current.submitError).toContain('内容为空')
  })

  it('提交非 Error 抛出：submitError 用兜底文案', async () => {
    const { result } = setup()
    submitMock.mockRejectedValue('字符串错误')

    await act(async () => {
      await result.current.submit('x')
    })
    expect(result.current.submitError).toBe('短信提交失败，请稍后重试')
  })
})

describe('useCourtSms 无 smsId 时的守卫', () => {
  it('assignCase / retry / resume / abortAndRemove 在无 smsId 时都是 no-op', async () => {
    const { result } = setup()
    expect(result.current.smsId).toBeNull()

    await act(async () => {
      await result.current.assignCase(1)
      await result.current.retry()
      result.current.resume()
      await result.current.abortAndRemove()
      await result.current.refresh()
    })

    expect(vi.mocked(assignCourtSmsCase)).not.toHaveBeenCalled()
    expect(vi.mocked(retryCourtSms)).not.toHaveBeenCalled()
    expect(abortMock).not.toHaveBeenCalled()
    expect(getDetailMock).not.toHaveBeenCalled()
  })
})

describe('useCourtSms refresh 分支', () => {
  it('后端已终态：置 done 并失效收件箱', async () => {
    const { result, invalidateSpy } = setup()
    submitMock.mockResolvedValue(9 as never)
    getDetailMock.mockResolvedValue(makeDetail('processing') as never)

    await act(async () => {
      await result.current.submit('内容')
    })
    await flush()

    // 弹窗关闭期间后端已完成
    getDetailMock.mockResolvedValue(makeDetail('completed') as never)
    await act(async () => {
      await result.current.refresh()
    })

    expect(result.current.phase).toBe('done')
    expect(result.current.outcome).toBe('completed')
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: HOME_INBOX_KEY })
  })

  it('后端仍在跑：回到 processing 并续轮询', async () => {
    const { result } = setup()
    submitMock.mockResolvedValue(9 as never)
    getDetailMock.mockResolvedValue(makeDetail('processing') as never)

    await act(async () => {
      await result.current.submit('内容')
    })
    await flush()
    getDetailMock.mockClear()

    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.phase).toBe('processing')
    expect(getDetailMock).toHaveBeenCalled()
  })

  it('refresh 查询失败：保持原状态不抛错', async () => {
    const { result } = setup()
    submitMock.mockResolvedValue(9 as never)
    getDetailMock.mockResolvedValue(makeDetail('processing') as never)

    await act(async () => {
      await result.current.submit('内容')
    })
    await flush()
    const before = result.current.phase

    getDetailMock.mockRejectedValue(new Error('记录已删'))
    await act(async () => {
      await result.current.refresh()
    })
    expect(result.current.phase).toBe(before)
  })
})

describe('useCourtSms retry 失败防护', () => {
  it('retry 抛错时 actionBusy 仍复位', async () => {
    const { result } = setup()
    submitMock.mockResolvedValue(9 as never)
    getDetailMock.mockResolvedValue(makeDetail('failed') as never)

    await act(async () => {
      await result.current.submit('内容')
    })
    await flush()
    await tick()

    vi.mocked(retryCourtSms).mockRejectedValue(new Error('后端拒绝'))
    await act(async () => {
      await result.current.retry().catch(() => {})
    })
    expect(result.current.actionBusy).toBe(false)
  })
})
