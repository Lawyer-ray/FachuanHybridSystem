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
  courtSmsHistoryKeys,
  getCourtSmsDetail,
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
