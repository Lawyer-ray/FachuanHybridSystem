/**
 * 多标签页抢占（node）：同一条 `ui_action` 只让一个标签页执行。
 *
 * ## 为什么抢占逻辑单独一个文件
 *
 * 它与「一条动作在本标签页内怎么执行」是两件事：这里测的是**跨页面实例**的归属
 * （谁有资格执行），坏掉的样子也不一样——执行态全绿、页面真的动了，只是一条写库
 * 动作被执行了两遍、两条回执各说各的。理由与 TTL 取值的论证见
 * `store/ui-action-claim.ts` 的文件头。
 *
 * ## 为什么用假 storage / 假时钟
 *
 * 「别的标签页正在飞这条动作」在真实浏览器里要开两个页面才能复现，而 TTL 要等 15 秒
 * 才过期。`claimUiActionExecution` 的 `ports` 就是为此留的注入点：`storage` 换成
 * `Map` 包一层的假货，`now` 换成可拨的时钟，等待与并发都变成一次函数调用。
 *
 * 集成用例里 `localStorage` 必须换成全局桩：`runUiAction` 走的是默认端口
 * （`globalThis.localStorage`），不注入。node 环境本来没有这个全局，所以这条用例
 * 同时也是「有 localStorage 时不误伤正常执行」的对照。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useCopilot } from './store'
import {
  CLAIM_PREFIX,
  CLAIM_TTL_MS,
  claimUiActionExecution,
  type ClaimStorage,
} from './store/ui-action-claim'
import { setUiToolPorts } from './store/ui-tools'
import { ackUiActionResult } from './ui-tools/ack'

// 回执的替身：抢不到执行权的那一侧「一发都不能发」，只能从模块边界上数
vi.mock('./ui-tools/ack', () => ({ ackUiActionResult: vi.fn() }))

vi.mock('./api', () => ({
  createSession: vi.fn(),
  fetchHistory: vi.fn(),
  openMessageStream: vi.fn(),
  decideApproval: vi.fn(),
  listSessions: vi.fn(),
  deleteSession: vi.fn(),
  steerSession: vi.fn(),
  clearSessionQueue: vi.fn(),
  submitAgentTask: vi.fn(),
  fetchPendingApprovals: vi.fn(),
  uploadAttachment: vi.fn(),
  answerQuestion: vi.fn(),
  fetchPendingQuestions: vi.fn(),
  submitUiActionResult: vi.fn(),
}))

/** 假的 localStorage：`Map` 包一层，只实现抢占用到的三个方法；`entries` 供断言残留键 */
function makeStorage() {
  const map = new Map<string, string>()
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    removeItem: (key: string) => void map.delete(key),
    entries: () => [...map.entries()],
  }
}

/** 宿主端口的替身：执行器只能通过它碰到浏览器 */
function makePorts() {
  return {
    navigate: vi.fn(),
    currentPath: vi.fn(() => '/'),
    toast: vi.fn(),
    dispatch: vi.fn(),
    openCopilot: vi.fn(),
  }
}

let ports: ReturnType<typeof makePorts>

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.getState().reset()
  ports = makePorts()
  setUiToolPorts(ports)
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('多标签页抢占：claimUiActionExecution', () => {
  it('同一条 callId 连抢两次：第一次赢，第二次让给对面（值为抢占时刻）', () => {
    const storage = makeStorage()
    const now = () => 1_000_000

    expect(claimUiActionExecution('c1', { now, storage })).toBe(true)
    expect(claimUiActionExecution('c1', { now, storage })).toBe(false)
    expect(storage.entries()).toEqual([[CLAIM_PREFIX + 'c1', '1000000']])
  })

  it('过期即可接手：时钟前进 20 秒后第二次能抢到，并覆盖成新时刻', () => {
    const storage = makeStorage()
    let at = 1_000_000
    const now = () => at

    expect(claimUiActionExecution('c2', { now, storage })).toBe(true)
    at += 20_000
    expect(claimUiActionExecution('c2', { now, storage })).toBe(true)
    // 覆盖而不是并存：一个 callId 只留一条，崩溃的标签页不许永久占着
    expect(storage.entries()).toEqual([[CLAIM_PREFIX + 'c2', String(at)]])
  })

  it('TTL 边界：差 1 毫秒仍算对面在飞，正好到 TTL 就算过期', () => {
    const storage = makeStorage()
    const claimedAt = 1_000_000
    let at = claimedAt
    const now = () => at

    expect(claimUiActionExecution('c2b', { now, storage })).toBe(true)
    at = claimedAt + CLAIM_TTL_MS - 1
    expect(claimUiActionExecution('c2b', { now, storage })).toBe(false)
    at = claimedAt + CLAIM_TTL_MS
    expect(claimUiActionExecution('c2b', { now, storage })).toBe(true)
  })

  it('不同 callId 互不影响：两条各自的第一次都抢到', () => {
    const storage = makeStorage()
    const now = () => 1_000_000

    expect(claimUiActionExecution('c3-a', { now, storage })).toBe(true)
    expect(claimUiActionExecution('c3-b', { now, storage })).toBe(true)
    expect(storage.entries().map(([key]) => key)).toEqual([CLAIM_PREFIX + 'c3-a', CLAIM_PREFIX + 'c3-b'])
  })

  it('拿不到 localStorage：返回 true 照常执行，且只 warn 一次', () => {
    // 本用例是文件里**唯一**踩到「storage 不可用」的用例：warn 抑制是模块级布尔，
    // 在它之前踩到就会让这条计数变成 0。新用例要么排在它后面，要么自带预期。
    const throwing: ClaimStorage = {
      getItem: () => {
        throw new Error('SecurityError')
      },
      setItem: () => {
        throw new Error('SecurityError')
      },
      removeItem: () => {
        throw new Error('SecurityError')
      },
    }
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    // 宁可重复执行，也不能什么都不做：两个标签页都抢不到存储时各执行一次，
    // 比「两个都不执行、模型等超时」好
    expect(claimUiActionExecution('c4', { storage: throwing })).toBe(true)
    expect(claimUiActionExecution('c4-again', { storage: throwing })).toBe(true)
    expect(warn).toHaveBeenCalledTimes(1)
  })
})

describe('store：抢不到执行权时静默返回', () => {
  it('预置未过期的抢占键：执行器不被调用、不发回执、不落运行记录', async () => {
    // 对照：没被抢占的动作照常执行并回执一次。没有这一段，「ack 没被调用」也可能
    // 只是替身没接上链路的假绿。
    const control = { callId: 'multi-control', action: 'ui_navigate', args: { path: '/projects' }, route: null }
    await useCopilot.getState().runUiAction(control)
    expect(ports.navigate).toHaveBeenCalledTimes(1)
    expect(vi.mocked(ackUiActionResult)).toHaveBeenCalledTimes(1)

    vi.clearAllMocks()
    const storage = makeStorage()
    storage.setItem(CLAIM_PREFIX + 'multi-1', String(Date.now()))
    vi.stubGlobal('localStorage', storage)

    await useCopilot.getState().runUiAction({
      callId: 'multi-1',
      action: 'ui_navigate',
      args: { path: '/material-prep' },
      route: null,
    })

    expect(ports.navigate).not.toHaveBeenCalled()
    // 回执由抢到的那个标签页发：这里再发一份，后端会看到自相矛盾的两个结局
    expect(vi.mocked(ackUiActionResult)).not.toHaveBeenCalled()
    // 也不落运行记录：横幅不该在没执行的标签页上报「AI 正在操作」
    expect(useCopilot.getState().uiToolRuns['multi-1']).toBeUndefined()
  })

  it('抢到执行权的那一侧照常跑完整条链路（回执也只发一次）', async () => {
    vi.stubGlobal('localStorage', makeStorage())
    const req = { callId: 'multi-2', action: 'ui_navigate', args: { path: '/settings' }, route: null }

    await useCopilot.getState().runUiAction(req)

    expect(ports.navigate).toHaveBeenCalledTimes(1)
    expect(vi.mocked(ackUiActionResult)).toHaveBeenCalledTimes(1)
  })
})
