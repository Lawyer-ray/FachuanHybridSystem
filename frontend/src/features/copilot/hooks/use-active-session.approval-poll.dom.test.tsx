// @vitest-environment jsdom
/**
 * `useActiveSession` 的待审列表补拉（jsdom + fake timers）。
 *
 * 补的是真机手测踩到的静默缺口：律师**没在跟**某个会话时（面板开着、但那一栏不在
 * 流式输出），新弹的审批卡不会自己浮出来——只在 sessionId / streaming 变化时拉一次的
 * 那版实现里，卡要等到他切会话或发下一句才出现。而服务端闸门等满 150 秒就按拒绝处理，
 * 于是律师看到的是「AI 的动作被拒绝了」，那张卡他一次都没见过。
 *
 * 五条不变量（外加「切会话不叠定时器」）：
 * - 非流式时按固定间隔反复拉，不是只拉一次；
 * - 流式中不拉（本轮的卡走 SSE 帧），从非流式转进去时定时器立刻停；
 * - 没有当前会话时不拉（没有该收的卡）；
 * - 标签页切到后台时跳过这一次，切回前台恢复；
 * - 卸载（宿主关闭）后不再拉——留着一个后台打接口的定时器是最常见的那种漏。
 *
 * 用**真实 store**：被测的就是「真实 store 的装配 + 真实定时器节奏」，把 store mock 掉
 * 等于自己跟自己演。只 mock 网络层（`../api`），用「有没有打 `/approvals/pending`」
 * （`fetchPendingApprovals`）当观测点——它是补拉唯一的可观测副作用。
 */
import type { ReactNode } from 'react'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  listSessions: vi.fn(),
  fetchBackends: vi.fn(),
  fetchHistory: vi.fn(),
  fetchSessionStats: vi.fn(),
  fetchPendingApprovals: vi.fn(),
  fetchPendingQuestions: vi.fn(),
}))

vi.mock('../api', () => apiMock)

import { useCopilot } from '../store'
import { APPROVAL_POLL_INTERVAL_MS, useActiveSession } from './use-active-session'

/** 打了多少次 `/approvals/pending`（补拉的唯一可观测副作用） */
function approvalPulls(): number {
  return apiMock.fetchPendingApprovals.mock.calls.length
}

/** 挂载 hook（宿主侧只需要一个 QueryClient：会话列表查询要用） */
function renderActiveSession() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return renderHook(() => useActiveSession(), {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    ),
  })
}

/** 冲掉挂载时那批 async 装配（switchSession / loadBackends / 首次补拉）的微任务 */
async function flush(): Promise<void> {
  await act(async () => {})
}

/** 推进假时钟并把期间产生的微任务/状态更新一起冲干净 */
async function advance(ms: number): Promise<void> {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms)
  })
}

/** 覆盖 jsdom 的 `document.visibilityState`（原型上是只读 getter，只能在实例上盖） */
function setVisibility(state: DocumentVisibilityState): void {
  Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => state })
}

/** 删掉实例上的覆盖，露出 jsdom 原型默认的 `visible` */
function restoreVisibility(): void {
  Reflect.deleteProperty(document, 'visibilityState')
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.clearAllMocks()
  useCopilot.getState().reset()
  apiMock.listSessions.mockResolvedValue([])
  apiMock.fetchBackends.mockResolvedValue([])
  apiMock.fetchHistory.mockResolvedValue([])
  // 水位是增强信息（store 内部静默），这里让它失败即可
  apiMock.fetchSessionStats.mockRejectedValue(new Error('不关心'))
  apiMock.fetchPendingApprovals.mockResolvedValue([])
  apiMock.fetchPendingQuestions.mockResolvedValue([])
})

afterEach(() => {
  restoreVisibility()
  vi.useRealTimers()
})

describe('useActiveSession：待审列表补拉', () => {
  it('非流式时每 8 秒补拉一次（不是只在切会话时拉过一次）', async () => {
    useCopilot.setState({ sessionId: 's-1', streaming: false })
    renderActiveSession()
    await flush()
    const mounted = approvalPulls()
    expect(mounted).toBe(1)

    // 差 1 毫秒不算到点：间隔就是常量写的那个值，不是「大约」
    await advance(APPROVAL_POLL_INTERVAL_MS - 1)
    expect(approvalPulls()).toBe(mounted)

    await advance(1)
    expect(approvalPulls()).toBe(mounted + 1)

    // 而且是**持续**轮：再过一个间隔又拉一次（一次性的补救挡不住「律师一直没动」）
    await advance(APPROVAL_POLL_INTERVAL_MS)
    expect(approvalPulls()).toBe(mounted + 2)
  })

  it('流式中不补拉（本轮的卡走 SSE 帧）', async () => {
    useCopilot.setState({ sessionId: 's-1', streaming: true })
    renderActiveSession()
    await flush()

    // 流式时连挂载那一次也不拉（既有口径：帧会送到，重复拉是浪费）
    expect(approvalPulls()).toBe(0)
    await advance(APPROVAL_POLL_INTERVAL_MS * 3)
    expect(approvalPulls()).toBe(0)
  })

  it('从非流式转成流式：定时器立刻停，之后不再补拉', async () => {
    useCopilot.setState({ sessionId: 's-1', streaming: false })
    renderActiveSession()
    await flush()
    const mounted = approvalPulls()

    await act(async () => {
      useCopilot.setState({ streaming: true })
    })
    await advance(APPROVAL_POLL_INTERVAL_MS * 3)
    expect(approvalPulls()).toBe(mounted)
  })

  it('没有当前会话时不补拉（没有该收的卡）', async () => {
    useCopilot.setState({ sessionId: null, streaming: false })
    renderActiveSession()
    await flush()
    // 挂载时那一次仍会发生（store 内部按 sessionId 过滤），但之后不该再有
    const mounted = approvalPulls()

    await advance(APPROVAL_POLL_INTERVAL_MS * 3)
    expect(approvalPulls()).toBe(mounted)
  })

  it('标签页切到后台时跳过这一次，切回前台恢复', async () => {
    useCopilot.setState({ sessionId: 's-1', streaming: false })
    renderActiveSession()
    await flush()
    const mounted = approvalPulls()

    setVisibility('hidden')
    await advance(APPROVAL_POLL_INTERVAL_MS * 2)
    expect(approvalPulls()).toBe(mounted)

    setVisibility('visible')
    await advance(APPROVAL_POLL_INTERVAL_MS)
    expect(approvalPulls()).toBe(mounted + 1)
  })

  it('切会话不叠出第二个定时器（cleanup 在 sessionId 变化时生效）', async () => {
    useCopilot.setState({ sessionId: 's-1', streaming: false })
    renderActiveSession()
    await flush()

    await act(async () => {
      useCopilot.setState({ sessionId: 's-2' })
    })
    await flush()
    const switched = approvalPulls()

    // 一个间隔只有一次：漏了 cleanup 的话旧会话的定时器还在跳，这里会拿到 +2
    await advance(APPROVAL_POLL_INTERVAL_MS)
    expect(approvalPulls()).toBe(switched + 1)
  })

  it('卸载后不再补拉（宿主关闭不留后台打接口的定时器）', async () => {
    useCopilot.setState({ sessionId: 's-1', streaming: false })
    const { unmount } = renderActiveSession()
    await flush()
    const mounted = approvalPulls()

    unmount()
    await advance(APPROVAL_POLL_INTERVAL_MS * 3)
    expect(approvalPulls()).toBe(mounted)
  })
})
