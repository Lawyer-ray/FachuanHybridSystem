// @vitest-environment jsdom
/**
 * useDocParse 轮询会话竞态回归单测（jsdom + fake timers）。
 *
 * mock 只打 api 层（../../api = home/api）：parseDocument / getParseTaskTask。
 * 重点覆盖旧实现的缺陷：submit 重入时「正在 await 网络请求」的旧轮询停不下来，
 * 旧任务迟到的终态会写进 state 覆盖新提交（会话号守卫后必须自检退出）。
 * 注意 submit 内部 `await pollTask(...)` 会陪轮询到终态，测试统一用 startSubmit
 * 「发起后冲微任务」再按需推进计时器，不能直接 await submit。
 */
import { act, renderHook } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api', () => ({
  parseDocument: vi.fn(),
  getParseTaskTask: vi.fn(),
  DOC_PARSE_MAX_POLLS: 150,
  DOC_PARSE_POLL_MS: 2000,
  // hook 终态会 invalidate 该 key（无需真实查询，仅需形状存在）
  parseHistoryKeys: { all: ['doc-parse-history'] },
}))

import { getParseTaskTask, parseDocument } from '../../api'
import type { ParseOutcome, ParseTaskStatus } from '../../api'

import { useDocParse } from './use-doc-parse'

const parseMock = vi.mocked(parseDocument)
const getTaskMock = vi.mocked(getParseTaskTask)

const TICK = 2000

/** 构造极简 outcome：ok/error 即可区分来源 */
function makeOutcome(ok: boolean, error: string | null): ParseOutcome {
  return { ok, markdown: '', text: '', method: null, error, metadata: {} }
}

function makeStatus(taskId: string, status: ParseTaskStatus['status'], outcome: ParseOutcome | null): ParseTaskStatus {
  return { taskId, status, outcome }
}

/** 上传返回待轮询任务（云端异步路径） */
function submitOf(taskId: string) {
  return { taskId, status: 'pending', outcome: null }
}

type HookResult = ReturnType<typeof useDocParse>

function setup() {
  // hook 内 useQueryClient invalidate 历史 key，需要 Provider 包裹
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return renderHook(() => useDocParse(), {
    wrapper: ({ children }) => <QueryClientProvider client={client}>{children}</QueryClientProvider>,
  })
}

/** 发起 submit 但不等待（其内部 await pollTask 会陪到终态），只冲微任务让上传落地 */
async function startSubmit(
  result: { current: HookResult },
  name = 'a.pdf',
): Promise<void> {
  await act(async () => {
    void result.current.submit(new File(['x'], name), {
      backend: 'auto',
      extractTables: false,
      extractImages: false,
      returnMarkdown: true,
    })
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

describe('useDocParse 重提交 / 失效竞态回归', () => {
  it('重提交：旧任务在飞的轮询响应迟到，也不得把旧终态写进 state 覆盖新提交', async () => {
    const outcomeA = makeOutcome(true, null)
    const outcomeB = makeOutcome(false, 'B 解析失败')
    // 第一次提交返回任务 A，第二次返回任务 B
    parseMock.mockResolvedValueOnce(submitOf('A')).mockResolvedValueOnce(submitOf('B'))
    let resolveA!: (v: ParseTaskStatus) => void
    getTaskMock.mockImplementation((id: string) => {
      if (id === 'A') {
        // A 的首轮查询悬住：模拟「正在 await 网络」的旧循环
        return new Promise<ParseTaskStatus>((resolve) => {
          resolveA = resolve
        })
      }
      return Promise.resolve(makeStatus('B', 'failure', outcomeB))
    })

    const { result } = setup()
    await startSubmit(result, 'a.pdf')
    expect(result.current.phase).toBe('polling')
    expect(getTaskMock).toHaveBeenCalledWith('A')

    // A 的查询还在飞时提交 B：旧会话即刻失效
    await startSubmit(result, 'b.pdf')
    expect(result.current.phase).toBe('done')
    expect(result.current.outcome).toEqual(outcomeB)

    // A 的终态此刻才返回——旧循环醒来必须自检退出，不写任何 state
    await act(async () => {
      resolveA(makeStatus('A', 'success', outcomeA))
      await vi.advanceTimersByTimeAsync(0)
    })
    expect(result.current.outcome).toEqual(outcomeB)
    expect(result.current.phase).toBe('done')

    // 旧循环彻底死透：继续走表也不会再查 A
    const calls = getTaskMock.mock.calls.length
    await tick(TICK * 3)
    expect(getTaskMock.mock.calls.length).toBe(calls)
  })

  it('重提交后旧循环停止轮询旧任务 id：计时器推进只服务新任务', async () => {
    parseMock.mockResolvedValueOnce(submitOf('A')).mockResolvedValueOnce(submitOf('B'))
    // A 永远 pending（若旧循环未被会话失效，会一直打 A 的查询）
    getTaskMock.mockImplementation((id: string) =>
      Promise.resolve(id === 'A' ? makeStatus('A', 'running', null) : makeStatus('B', 'running', null)),
    )

    const { result } = setup()
    await startSubmit(result, 'a.pdf')
    await tick(TICK * 2)
    expect(getTaskMock).toHaveBeenCalledWith('A')

    await startSubmit(result, 'b.pdf')
    const callsWithA = getTaskMock.mock.calls.filter(([id]) => id === 'A').length
    await tick(TICK * 5)
    // B 继续轮询，A 的查询次数不再增长
    expect(getTaskMock.mock.calls.some(([id]) => id === 'B')).toBe(true)
    expect(getTaskMock.mock.calls.filter(([id]) => id === 'A').length).toBe(callsWithA)
  })

  it('reset：轮询中回到 idle，旧循环不再打接口', async () => {
    parseMock.mockResolvedValue(submitOf('A'))
    getTaskMock.mockResolvedValue(makeStatus('A', 'running', null))
    const { result } = setup()

    await startSubmit(result)
    expect(result.current.phase).toBe('polling')

    act(() => {
      result.current.reset()
    })
    expect(result.current.phase).toBe('idle')
    expect(result.current.outcome).toBeNull()

    const calls = getTaskMock.mock.calls.length
    await tick(TICK * 3)
    expect(getTaskMock.mock.calls.length).toBe(calls)
  })

  it('卸载：挂起的 sleep 被唤醒收尾，卸载后不再打接口', async () => {
    parseMock.mockResolvedValue(submitOf('A'))
    getTaskMock.mockResolvedValue(makeStatus('A', 'running', null))
    const { result, unmount } = setup()

    await startSubmit(result)
    expect(result.current.phase).toBe('polling')

    unmount()
    const calls = getTaskMock.mock.calls.length
    await tick(TICK * 3)
    expect(getTaskMock.mock.calls.length).toBe(calls)
  })
})
