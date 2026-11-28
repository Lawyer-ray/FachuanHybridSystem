/**
 * store 的 `guarded` 二次确认闸门（node）：没有律师点头，执行器一次都不许跑。
 *
 * ## 这条闸门坏掉的两种样子（都不会报错）
 *
 * 1. **放行**：确认宿主没挂载（面板收起 / 灰度期旧前端 / 前端挂载失败）时直接执行——
 *    删除这类不可逆动作在无人确认的情况下发生，日志里只有一条正常的 `ok`；
 * 2. **卡死**：确认框点完之后没有把「不同意」翻译成 `aborted`，运行记录停在 `running`、
 *    后端等不到回执，模型于是原样重发一次写动作。
 *
 * 所以这里断言的不是「有没有弹框」，而是三件可观察的事实：执行器没跑 / 落了 `aborted`
 * 运行记录 / 回执里写清了「律师取消」。
 *
 * ## 为什么用受控执行器而不是真链路
 *
 * 真执行器会打 HTTP（`deletePack` → `DELETE /inbox/messages/{id}`），node 单测既不该发
 * 网络请求，也证不了「哪条动作被放行」——而后者正是本文件的被测对象。真清单 + 真执行器
 * 的完备性由 `ui-tools/registry.node.test.ts`（每条清单动作都能 resolve 到执行器）与
 * `material-prep/ui-actions.node.test.ts`（执行器真的调 `deletePack`）守。
 *
 * 每个用例的 callId 都不同：`seenCallIds` 是模块级 LRU，复用同一个 id 会让后一个用例
 * 被前一个静默挡掉。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'
import { setUiToolPorts } from './store/ui-tools'
import { setGuardedConfirmHandler } from './store/ui-guarded-confirm'
import type { GuardedConfirmRequest } from './store/ui-guarded-confirm'
import type { UiToolRun } from './state-types'
import type { UiToolOutcome } from './ui-tools'

/** 执行器替身：记录**真的被执行**的那几条 callId（闸门要挡的就是它） */
const mockExec = vi.hoisted(() => ({ executed: [] as string[], outcome: { ok: true, detail: '执行过了' } }))

vi.mock('./ui-tools', () => ({
  UI_TOOL_SPECS: [
    {
      name: 'ui_material_prep_delete_pack',
      title: '删除材料包（不可恢复）',
      describe: '',
      argsSchema: {
        type: 'object',
        properties: { packId: { type: 'integer' } },
        required: ['packId'],
        additionalProperties: false,
      },
      route: '/material-prep',
      risk: 'guarded',
      tier: 'direct',
      handler: 'material_prep_delete_pack',
      idempotent: false,
      undo: 'none',
    },
    {
      name: 'ui_material_prep_judge',
      title: '判定材料包归属',
      describe: '',
      argsSchema: {
        type: 'object',
        properties: { packId: { type: 'integer' }, target: { type: 'string' } },
        required: ['packId', 'target'],
        additionalProperties: false,
      },
      route: '/material-prep',
      risk: 'confirm',
      tier: 'direct',
      handler: 'material_prep_judge',
      idempotent: false,
      undo: 'none',
    },
  ],
  validateArgs: () => true,
  runUiTool: (req: { callId: string }) => {
    mockExec.executed.push(req.callId)
    return mockExec.outcome as UiToolOutcome
  },
}))

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
  // 回执：取消也要发（不发，后端只能等到超时、模型以为动作还在跑）
  submitUiActionResult: vi.fn(),
}))

/** 宿主端口的替身：执行器只能通过它碰到浏览器 */
function makePorts() {
  return {
    navigate: vi.fn(),
    currentPath: vi.fn(() => '/material-prep'),
    toast: vi.fn(),
    dispatch: vi.fn(),
    openCopilot: vi.fn(),
  }
}

let ports: ReturnType<typeof makePorts>

/** 窄口径读运行记录：缺项时给出可读的失败信息，而不是 undefined 引发的 TypeError */
function runOf(callId: string): UiToolRun {
  const run = useCopilot.getState().uiToolRuns[callId]
  if (!run) throw new Error(`缺少 callId=${callId} 的运行记录`)
  return run
}

/**
 * 发起一次 guarded 删除（参数与清单同形）。
 *
 * `packId` 每个用例都要不同：这条动作 `idempotent: false`，store 的「同参 5 秒窗」
 * 是**模块级**的，两个用例共用 `{packId: 812}` 会让后一个被悄悄挡掉
 * （症状：执行器一次没调、也没有任何运行记录）。
 */
function deleteRequest(callId: string, packId: number) {
  return { callId, action: 'ui_material_prep_delete_pack', args: { packId }, route: '/material-prep' }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockExec.executed.length = 0
  mockExec.outcome = { ok: true, detail: '执行过了' }
  useCopilot.getState().reset()
  ports = makePorts()
  setUiToolPorts(ports)
})

afterEach(() => {
  // 宿主槽位是模块级状态：留在那里会让下一个文件的用例以为「有确认框」
  setGuardedConfirmHandler(null)
  vi.restoreAllMocks()
})

describe('guarded：执行前必须先过本地二次确认', () => {
  it('没有登记确认宿主 → 不执行、落 aborted、回执写明律师取消（fail closed）', async () => {
    setGuardedConfirmHandler(null)
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {})

    await useCopilot.getState().runUiAction(deleteRequest('guarded-nohost-1', 812))

    // 执行器一次都不许跑：没有确认宿主就等于没人在问律师
    expect(mockExec.executed).toEqual([])
    expect(runOf('guarded-nohost-1')).toMatchObject({ state: 'aborted', code: 'aborted' })
    // 回执必须发：模型据此知道「没执行」，而不是以为它还在跑
    expect(copilotApi.submitUiActionResult).toHaveBeenCalledTimes(1)
    expect(vi.mocked(copilotApi.submitUiActionResult).mock.calls[0]?.[0]).toMatchObject({
      call_id: 'guarded-nohost-1',
      outcome: 'aborted',
      detail: '律师在二次确认里取消了',
    })
    // 不是失败：不弹错误 toast（吵闹一次没有意义），但必须 warn 说明闸门在起作用
    // （只断言与本次闸门有关的那一句：同一条链路上 localStorage 不可用也会 warn 一次）
    expect(ports.toast).not.toHaveBeenCalled()
    const gateWarnings = warn.mock.calls.filter((call) => String(call[0]).includes('[ui-guarded-confirm]'))
    expect(gateWarnings, '没有宿主时至少要留一条「guarded 不执行」的 warn').toHaveLength(1)
  })

  it('确认框里点了「取消」→ 不执行、落 aborted；请求里带着动作名 / 标题 / 参数 / callId', async () => {
    const handler = vi.fn(async (_req: GuardedConfirmRequest) => false)
    setGuardedConfirmHandler(handler)

    await useCopilot.getState().runUiAction(deleteRequest('guarded-cancel-1', 813))

    expect(mockExec.executed).toEqual([])
    expect(runOf('guarded-cancel-1')).toMatchObject({ state: 'aborted', code: 'aborted' })
    // 律师要能认出「是哪一个包」：标题与参数必须原样送到宿主手上
    expect(handler).toHaveBeenCalledWith({
      action: 'ui_material_prep_delete_pack',
      title: '删除材料包（不可恢复）',
      args: { packId: 813 },
      callId: 'guarded-cancel-1',
    })
    expect(vi.mocked(copilotApi.submitUiActionResult).mock.calls[0]?.[0]).toMatchObject({
      outcome: 'aborted',
      detail: '律师在二次确认里取消了',
    })
  })

  it('确认框里点了「确认执行」→ 真的执行，落 ok 并回执', async () => {
    const handler = vi.fn(async (_req: GuardedConfirmRequest) => true)
    setGuardedConfirmHandler(handler)

    await useCopilot.getState().runUiAction(deleteRequest('guarded-ok-1', 814))

    expect(mockExec.executed).toEqual(['guarded-ok-1'])
    expect(runOf('guarded-ok-1')).toMatchObject({ state: 'ok' })
    expect(vi.mocked(copilotApi.submitUiActionResult).mock.calls[0]?.[0]).toMatchObject({
      call_id: 'guarded-ok-1',
      outcome: 'ok',
    })
  })

  it('确认宿主自己抛异常 → 按「律师没同意」处理（不执行、不冒泡成未处理 rejection）', async () => {
    setGuardedConfirmHandler(async () => {
      throw new Error('对话框挂了')
    })
    vi.spyOn(console, 'warn').mockImplementation(() => {})

    await useCopilot.getState().runUiAction(deleteRequest('guarded-boom-1', 815))

    expect(mockExec.executed).toEqual([])
    expect(runOf('guarded-boom-1')).toMatchObject({ state: 'aborted', code: 'aborted' })
  })

  it('`confirm` 动作不弹确认（那档的批准在后端审批卡，多问一次只是噪音）', async () => {
    const handler = vi.fn(async (_req: GuardedConfirmRequest) => true)
    setGuardedConfirmHandler(handler)

    await useCopilot.getState().runUiAction({
      callId: 'confirm-1',
      action: 'ui_material_prep_judge',
      args: { packId: 816, target: 'done' },
      route: '/material-prep',
    })

    expect(handler).not.toHaveBeenCalled()
    expect(mockExec.executed).toEqual(['confirm-1'])
    expect(runOf('confirm-1')).toMatchObject({ state: 'ok' })
  })
})
