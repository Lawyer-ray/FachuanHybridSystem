/**
 * store 的界面动作回执（node）：三种结算各发一次，且**回执不拖慢动作**。
 *
 * 为什么单独一个文件而不是塞进 `store.ui-tools.test.ts`：那个文件测的是执行态
 * （幂等 / 打断 / 落态），这里测的是「结算之后有没有把真实结果送回后端」。
 * 后者坏掉的样子和前者完全不同——运行记录全绿、页面真的跳了，模型却永远看到
 * `observed: false`（前端一个回执都没发），或者反过来：回执把动作的返回卡住，
 * 律师点一下要等两秒。
 *
 * 断言走真实链路：只替身 HTTP 边界（`../api`）与宿主端口，`runUiAction` → `runUiTool`
 * → 真执行器 → 端口 全是真货。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'
import { setUiToolPorts } from './store/ui-tools'
import type { UiActionResultAck } from './ui-tools/types'

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

/** 律师此刻真实所在的地址（回执里的 observed_location 必须报它） */
const CURRENT_LOCATION = '/material-prep?stage=todo'

/** 抽干微任务：回执的失败分支要跑到「等 300ms 重试」那一步才可观察 */
async function flushMicrotasks(): Promise<void> {
  for (let i = 0; i < 6; i += 1) await Promise.resolve()
}

/** 第 n 次回执的 payload（缺失即说明根本没发，给出可读失败信息而不是 TypeError） */
function ackPayload(index = 0): UiActionResultAck {
  const call = vi.mocked(copilotApi.submitUiActionResult).mock.calls[index]
  if (!call) throw new Error(`没有第 ${index + 1} 次回执：submitUiActionResult 没被调用`)
  return call[0]
}

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.getState().reset()
  ports = makePorts()
  setUiToolPorts(ports)
  // success=false 也是「已收到」，不抛：走的是同一条 resolve 路径
  vi.mocked(copilotApi.submitUiActionResult).mockResolvedValue({ accepted: true, success: true })
  // node 环境没有 window；真实实现读的正是 window.location（见 ui-tools/ack.ts）
  vi.stubGlobal('window', { location: { pathname: '/material-prep', search: '?stage=todo' } })
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('store: 界面动作回执', () => {
  it('ok：执行完发一次，detail 是执行器的真实结果，location 是执行后的地址', async () => {
    await useCopilot.getState().runUiAction({
      callId: 'ack-ok-1',
      action: 'ui_navigate',
      args: { path: '/projects' },
      route: null,
    })

    expect(copilotApi.submitUiActionResult).toHaveBeenCalledTimes(1)
    expect(ackPayload()).toEqual({
      call_id: 'ack-ok-1',
      outcome: 'ok',
      detail: '/projects',
      observed_location: CURRENT_LOCATION,
    })
  })

  it('error：带错误码与给律师看的那句话（白名单拦截 = route_unreachable）', async () => {
    await useCopilot.getState().runUiAction({
      callId: 'ack-err-1',
      action: 'ui_navigate',
      args: { path: 'javascript:alert(1)' },
      route: null,
    })

    expect(copilotApi.submitUiActionResult).toHaveBeenCalledTimes(1)
    expect(ackPayload()).toMatchObject({
      call_id: 'ack-err-1',
      outcome: 'error',
      code: 'route_unreachable',
      observed_location: CURRENT_LOCATION,
    })
    // 模型看到的 detail 与律师看到的提示是同一句话：两处文案一分叉，复盘就对不上
    expect(ackPayload().detail).toContain('白名单')
    expect(ports.toast).toHaveBeenCalledTimes(1)
  })

  it('aborted：律师点「停下」之后到达的动作也要回执（不发，后端只能等到超时）', async () => {
    useCopilot.getState().abortUiActions()
    await useCopilot.getState().runUiAction({
      callId: 'ack-ab-1',
      action: 'ui_navigate',
      args: { path: '/projects' },
      route: null,
    })

    expect(ports.navigate).not.toHaveBeenCalled()
    expect(copilotApi.submitUiActionResult).toHaveBeenCalledTimes(1)
    // 打断不带 code/detail：它不是失败，契约里 code 只在 error 时给
    expect(ackPayload()).toEqual({
      call_id: 'ack-ab-1',
      outcome: 'aborted',
      observed_location: CURRENT_LOCATION,
    })
  })

  it('runUiAction 不等回执：回执还挂在 300ms 重试窗里，动作早已结算', async () => {
    vi.useFakeTimers()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    // 回执必失败：这样它会占住整个重试窗，任何「等回执」的写法都会在这里卡死
    vi.mocked(copilotApi.submitUiActionResult).mockRejectedValue(new Error('后端那一跳不在了'))

    await useCopilot.getState().runUiAction({
      callId: 'ack-slow-1',
      action: 'ui_navigate',
      args: { path: '/projects' },
      route: null,
    })
    await flushMicrotasks()

    // ① 动作已经落完（跳了、运行记录是 ok）——这一行能执行到本身就是「没等回执」的证明：
    //    此刻回执的第二次尝试还排在 300ms 定时器上，`await` 它就不可能走到这里。
    expect(ports.navigate).toHaveBeenCalledTimes(1)
    expect(useCopilot.getState().uiToolRuns['ack-slow-1']).toMatchObject({ state: 'ok' })
    // ② 回执确实在飞、且只发了第一次（重试还没发生）
    expect(copilotApi.submitUiActionResult).toHaveBeenCalledTimes(1)
    expect(vi.getTimerCount()).toBe(1)

    // ③ 放手让回执走完：它失败到只 warn，也不会回头改动任何运行记录
    await vi.advanceTimersByTimeAsync(300)
    expect(copilotApi.submitUiActionResult).toHaveBeenCalledTimes(2)
    expect(warn).toHaveBeenCalledTimes(1)
    expect(useCopilot.getState().uiToolRuns['ack-slow-1']).toMatchObject({ state: 'ok' })
  })
})
