// @vitest-environment jsdom
/**
 * useConverterJob 轮询会话竞态回归单测（jsdom + fake timers）。
 *
 * mock 只打 api 层（../../api = home/api）：createConverterJob / getConverterJob。
 * 重点覆盖旧 DocConverterCard 内联轮询的缺陷：重提交时「正在 await 网络」的
 * 旧循环停不下来，旧 job 迟到的终态会写进 state 覆盖新提交
 * （会话号守卫后旧循环必须自检退出）。
 */
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api', () => ({
  createConverterJob: vi.fn(),
  getConverterJob: vi.fn(),
  // hook 终态会 invalidate 该 key（无需真实查询，仅需形状存在）
  converterHistoryKeys: { all: ['doc-converter-history'] },
}))

import { createConverterJob, getConverterJob } from '../../api'
import type { ConverterJob } from '../../api'

import { useConverterJob } from './use-converter-job'

const createMock = vi.mocked(createConverterJob)
const getJobMock = vi.mocked(getConverterJob)

const TICK = 2000

function makeJob(jobId: string, over: Partial<ConverterJob> = {}): ConverterJob {
  return { jobId, status: 'processing', total: 2, done: 0, failed: 0, items: [], ...over }
}

type HookResult = ReturnType<typeof useConverterJob>

function setup() {
  // hook 内 useQueryClient invalidate 历史 key，需要 Provider 包裹
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return renderHook(() => useConverterJob(), {
    wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  })
}

/** 发起 submit 但不等待（内部 poll 会陪到终态），只冲微任务让提交落地 */
async function startSubmit(result: { current: HookResult }, files = [new File(['x'], 'a.doc')]) {
  await act(async () => {
    void result.current.submit(files)
    await vi.advanceTimersByTimeAsync(0)
  })
}

async function tick(ms = TICK) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('useConverterJob 提交与终态', () => {
  it('提交 → 轮询推进 → 全部完成：phase=success、job 明细落地', async () => {
    createMock.mockResolvedValue('J1')
    getJobMock
      .mockResolvedValueOnce(makeJob('J1', { done: 1 }))
      .mockResolvedValueOnce(makeJob('J1', { status: 'completed', done: 2 }))
    const { result } = setup()

    expect(result.current.phase).toBe('idle')
    await startSubmit(result)
    expect(result.current.phase).toBe('running')
    expect(result.current.jobId).toBe('J1')

    await tick()
    expect(result.current.phase).toBe('success')
    expect(result.current.job).toMatchObject({ done: 2 })
    expect(result.current.error).toBeNull()
  })

  it('全部失败：phase=error 且带「确认 .doc」文案', async () => {
    createMock.mockResolvedValue('J1')
    getJobMock.mockResolvedValue(makeJob('J1', { status: 'failed', failed: 2 }))
    const { result } = setup()

    // 首轮查询在提交落地后即返回终态（fake timers 下不能用 waitFor，其内部轮询也被冻结）
    await startSubmit(result)
    await tick(0)
    expect(result.current.phase).toBe('error')
    expect(result.current.error).toBe('全部文件转换失败，请确认上传的是 .doc 文件')
  })

  it('轮询超时转 timeout，resume 恢复轮询并到终态', async () => {
    createMock.mockResolvedValue('J1')
    // 先 150 轮 pending 耗尽上限 → timeout；resume 后下一轮 completed
    getJobMock.mockResolvedValue(makeJob('J1', { total: 2, done: 1 }))
    const { result } = setup()

    await startSubmit(result)
    // 首查发生在提交落地后，之后每轮各隔 2s；第 150 轮查完再睡满一拍才转 timeout
    await tick(TICK * 150)
    expect(result.current.phase).toBe('timeout')

    getJobMock.mockResolvedValueOnce(makeJob('J1', { status: 'completed', done: 2 }))
    act(() => {
      result.current.resume()
    })
    await tick(0)
    expect(result.current.phase).toBe('success')
  })
})

describe('useConverterJob 重提交竞态回归', () => {
  it('重提交：旧 job 在飞的轮询响应迟到，也不得把旧终态写进 state 覆盖新提交', async () => {
    createMock.mockResolvedValueOnce('A').mockResolvedValueOnce('B')
    let resolveA!: (v: ConverterJob) => void
    getJobMock.mockImplementation((id: string) => {
      if (id === 'A') {
        // 旧 job 的首轮查询悬住：模拟「正在 await 网络」的旧轮询循环
        return new Promise<ConverterJob>((resolve) => {
          resolveA = resolve
        })
      }
      return Promise.resolve(makeJob('B', { status: 'failed', failed: 2 }))
    })

    const { result } = setup()
    await startSubmit(result)
    expect(result.current.phase).toBe('running')
    expect(getJobMock).toHaveBeenCalledWith('A')

    // 旧查询还在飞时提交 B：旧会话即刻失效，B 轮询到失败终态
    await startSubmit(result, [new File(['y'], 'b.doc')])
    expect(result.current.phase).toBe('error')
    expect(result.current.jobId).toBe('B')

    // 旧 job 的成功终态此刻才返回——旧循环醒来必须自检退出，不写任何 state
    await act(async () => {
      resolveA(makeJob('A', { status: 'completed', done: 2 }))
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.phase).toBe('error')
    expect(result.current.jobId).toBe('B')
    expect(result.current.job).toMatchObject({ jobId: 'B' })

    // 旧循环彻底死透：继续走表也不会再查 A
    const callsWithA = getJobMock.mock.calls.filter(([id]) => id === 'A').length
    await tick(TICK * 3)
    expect(getJobMock.mock.calls.filter(([id]) => id === 'A').length).toBe(callsWithA)
  })

  it('重提交后旧循环停止轮询旧 job id：计时器推进只服务新 job', async () => {
    createMock.mockResolvedValueOnce('A').mockResolvedValueOnce('B')
    // 两个 job 都永远 processing（旧循环若未被会话失效，会一直打 A 的查询）
    getJobMock.mockImplementation((id: string) => Promise.resolve(makeJob(id)))

    const { result } = setup()
    await startSubmit(result)
    await tick(TICK * 2)
    expect(getJobMock).toHaveBeenCalledWith('A')

    await startSubmit(result, [new File(['y'], 'b.doc')])
    const callsWithA = getJobMock.mock.calls.filter(([id]) => id === 'A').length
    await tick(TICK * 5)
    expect(getJobMock).toHaveBeenCalledWith('B')
    expect(getJobMock.mock.calls.filter(([id]) => id === 'A').length).toBe(callsWithA)
    expect(result.current.phase).toBe('running')
  })

  it('卸载：挂起的 sleep 被唤醒收尾，卸载后不再打接口', async () => {
    createMock.mockResolvedValue('A')
    getJobMock.mockResolvedValue(makeJob('A'))
    const { result, unmount } = setup()

    await startSubmit(result)
    expect(result.current.phase).toBe('running')

    unmount()
    const calls = getJobMock.mock.calls.length
    await tick(TICK * 3)
    expect(getJobMock.mock.calls.length).toBe(calls)
  })
})
