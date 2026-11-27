/**
 * store 的界面动作执行态（node）：幂等 / 打断 / 失败落态。
 *
 * 断言走**真实链路**：`./ui-tools` 不 mock，用的是真清单 + 真执行器。只测 store 自己
 * 的状态机测不出「前后端清单漂移」——而漂移的表现正是「模型调完页面毫无反应、日志里
 * 连错误都没有」，那必须由这条链路来证明。
 *
 * 每个用例的 callId 都不一样：幂等表是模块级 LRU（`reset()` 不清它，理由见
 * store/ui-tools.ts 文件头），共用同一个 id 会让后一个用例被前一个悄悄挡掉。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useCopilot } from './store'
import { setUiToolPorts } from './store/ui-tools'
import type { UiToolRun } from './state-types'

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

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.getState().reset()
  ports = makePorts()
  setUiToolPorts(ports)
})

/** 窄口径读运行记录：缺项时给出可读的失败信息，而不是 undefined 引发的 TypeError */
function runOf(callId: string): UiToolRun {
  const run = useCopilot.getState().uiToolRuns[callId]
  if (!run) throw new Error(`缺少 callId=${callId} 的运行记录`)
  return run
}

describe('store: 界面动作执行', () => {
  it('正常动作：执行器经端口真的跳转，并落 ok（不弹提示）', async () => {
    await useCopilot.getState().runUiAction({
      callId: 'nav-1',
      action: 'ui_navigate',
      args: { path: '/material-prep?stage=todo' },
      route: null,
    })

    expect(ports.navigate).toHaveBeenCalledTimes(1)
    // 只认第一个参数：执行器是否顺带传 { replace } 不是 store 的契约
    expect(ports.navigate.mock.calls[0]?.[0]).toBe('/material-prep?stage=todo')
    expect(runOf('nav-1')).toMatchObject({ name: 'ui_navigate', state: 'ok' })
    expect(ports.toast).not.toHaveBeenCalled()
  })

  it('同一 callId 重复投递只执行一次（模型重试 / 事件重放）', async () => {
    const req = { callId: 'dup-1', action: 'ui_navigate', args: { path: '/material-prep' }, route: null }
    await useCopilot.getState().runUiAction(req)
    await useCopilot.getState().runUiAction(req)

    expect(ports.navigate).toHaveBeenCalledTimes(1)
    expect(runOf('dup-1').state).toBe('ok')
  })

  it('「停下」之后到达的动作记 aborted，不执行也不弹提示', async () => {
    useCopilot.getState().abortUiActions()
    await useCopilot.getState().runUiAction({
      callId: 'ab-1',
      action: 'ui_navigate',
      args: { path: '/material-prep' },
      route: null,
    })

    expect(ports.navigate).not.toHaveBeenCalled()
    expect(runOf('ab-1')).toMatchObject({ state: 'aborted', code: 'aborted' })
    // 打断是律师主动按的，不是失败：再弹一条错误提示只是噪音
    expect(ports.toast).not.toHaveBeenCalled()
  })

  it('未知动作记 unknown_action 并提示（版本漂移不静默）', async () => {
    await useCopilot.getState().runUiAction({
      callId: 'unk-1',
      action: 'ui_teleport',
      args: {},
      route: null,
    })

    expect(runOf('unk-1')).toMatchObject({ state: 'error', code: 'unknown_action' })
    expect(ports.toast).toHaveBeenCalledTimes(1)
    expect(ports.navigate).not.toHaveBeenCalled()
  })

  it('参数不合法记 invalid_args，执行器根本不会被调用', async () => {
    await useCopilot.getState().runUiAction({
      callId: 'bad-1',
      action: 'ui_navigate',
      args: { path: 42 },
      route: null,
    })

    expect(runOf('bad-1')).toMatchObject({ state: 'error', code: 'invalid_args' })
    expect(ports.navigate).not.toHaveBeenCalled()
    expect(ports.toast).toHaveBeenCalledTimes(1)
  })

  it('恶意路径不落地：既没跳转，也没被当成成功', async () => {
    await useCopilot.getState().runUiAction({
      callId: 'evil-1',
      action: 'ui_navigate',
      args: { path: 'javascript:alert(1)' },
      route: null,
    })

    expect(ports.navigate).not.toHaveBeenCalled()
    // 具体错误码由 routes 白名单决定（route_unreachable / executor_error 都合理），
    // store 的职责是「不许静默成功」+ 让人看见
    expect(runOf('evil-1').state).toBe('error')
    expect(ports.toast).toHaveBeenCalledTimes(1)
  })

  it('宿主未挂载（面板与助手页都不在）时记失败，不调用执行器', async () => {
    setUiToolPorts(null)
    await useCopilot.getState().runUiAction({
      callId: 'nohost-1',
      action: 'ui_navigate',
      args: { path: '/material-prep' },
      route: null,
    })

    expect(runOf('nohost-1')).toMatchObject({ state: 'error', code: 'executor_error' })
  })
})

describe('store: 界面动作的会话清理', () => {
  it('reset() 清空运行记录与打断标记（否则换账号后横幅挂着一个不存在的操作）', async () => {
    await useCopilot.getState().runUiAction({
      callId: 'reset-1',
      action: 'ui_navigate',
      args: { path: '/material-prep' },
      route: null,
    })
    useCopilot.getState().abortUiActions()
    expect(useCopilot.getState().uiToolRuns['reset-1']).toBeTruthy()

    useCopilot.getState().reset()

    expect(useCopilot.getState().uiToolRuns).toEqual({})
    expect(useCopilot.getState().abortedAt).toBeNull()
  })
})
