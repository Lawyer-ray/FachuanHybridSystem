/**
 * store 的写动作互斥（node）：同一时刻只有一个 `risk !== 'safe'` 的动作在飞。
 *
 * ## 为什么这里必须用受控执行器（别的 store 测试都走真链路）
 *
 * 要证明「第一条没结算，第二条不许开始」，就得让执行停在半路；真执行器是毫秒级的同步
 * 动作，串行与并发在断言上长得一模一样（两者都「瞬间跑完」）。所以 `runUiTool` 换成受控
 * Promise：谁开始了、谁还在排队，全看得到。清单漂移仍由 `store.ui-tools.test.ts` 与
 * `ui-action.e2e.dom.test.tsx` 用真链路守住。
 *
 * ## 为什么清单只放两条（一条 confirm + 一条 safe）
 *
 * 写锁的判据只有 `spec.risk`，两条就够覆盖两侧：`ui_material_prep_judge`（真清单里的
 * `confirm`，执行器就是 read-modify-write）与 `ui_navigate`（`safe`）。safe 那侧必须一起
 * 测——把跳页也串进写锁不会报错、不会红，只会让律师觉得「点了没反应」。
 *
 * 每个用例的 callId 都不同，`packId` 更是全文件递增：幂等表 `seenCallIds` 与非幂等动作
 * 的同参 5 秒窗都是**模块级**的（`reset()` 不清它们）。复用同一个 id 会让后一个用例被
 * 悄无声息地挡掉——症状是「执行器一次都没被调用、也没有任何运行记录」，极难归因。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'
import { setUiToolPorts } from './store/ui-tools'
import type { UiToolRun } from './state-types'
import type { UiToolOutcome } from './ui-tools'

/**
 * 受控执行器：`started` 记录**开始执行**的顺序（存 callId），`pending` 让每条停在半路。
 *
 * 用 `vi.hoisted` 是因为 `vi.mock` 的工厂被提升到 import 之前，直接引用模块级变量会报
 * 「Cannot access before initialization」。
 */
const mockExec = vi.hoisted(() => {
  const started: string[] = []
  const pending = new Map<string, (outcome: unknown) => void>()
  return { started, pending }
})

vi.mock('./ui-tools', () => ({
  UI_TOOL_SPECS: [
    {
      name: 'ui_navigate',
      title: '跳转页面',
      describe: '',
      argsSchema: {
        type: 'object',
        properties: { path: { type: 'string' } },
        required: ['path'],
        additionalProperties: false,
      },
      route: null,
      risk: 'safe',
      tier: 'direct',
      handler: 'navigate',
      idempotent: true,
      undo: 'nav',
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
    mockExec.started.push(req.callId)
    return new Promise((resolve) => {
      mockExec.pending.set(req.callId, resolve)
    })
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
  // 结算回执：排队超限与打断也必须发（不发，后端只能等到超时）
  submitUiActionResult: vi.fn(),
}))

/** 结算某一条（resolve 执行器的受控 Promise） */
function settle(callId: string, outcome: UiToolOutcome): void {
  const resolve = mockExec.pending.get(callId)
  if (!resolve) throw new Error(`callId=${callId} 没有在等结算（它根本没开始执行）`)
  resolve(outcome)
}

/** 抽干微任务直到条件成立：整条链上只有 Promise，没有计时器 */
async function until(predicate: () => boolean, what: string): Promise<void> {
  for (let i = 0; i < 64; i += 1) {
    if (predicate()) return
    await Promise.resolve()
  }
  throw new Error(`等不到「${what}」`)
}

function runOf(callId: string): UiToolRun {
  const run = useCopilot.getState().uiToolRuns[callId]
  if (!run) throw new Error(`缺少 callId=${callId} 的运行记录`)
  return run
}

/** 运行态（还没落记录时返回 undefined）：给 `until` 的谓词用，不能抛 */
function stateOf(callId: string): string | undefined {
  return useCopilot.getState().uiToolRuns[callId]?.state
}

/** 某个 callId 最近一次回执（没发过返回 undefined） */
function ackOf(callId: string): { outcome?: string; code?: string; detail?: string } | undefined {
  const payloads = vi.mocked(copilotApi.submitUiActionResult).mock.calls.map(([payload]) => payload)
  for (let i = payloads.length - 1; i >= 0; i -= 1) {
    if (payloads[i]?.call_id === callId) return payloads[i]
  }
  return undefined
}

/** 全文件递增的 packId：同参 5 秒窗是模块级的，跨用例复用同一参数会被静默去重 */
let nextPackId = 1

/** 一条写动作（`risk: 'confirm'`，真清单里执行器就是 read-modify-write 的那条） */
function writeReq(callId: string) {
  nextPackId += 1
  return { callId, action: 'ui_material_prep_judge', args: { packId: nextPackId, target: 'done' }, route: null }
}

/** 一条 safe 动作（跳页）：毫秒级、高频，不该进写锁 */
function safeReq(callId: string) {
  return { callId, action: 'ui_navigate', args: { path: '/material-prep' }, route: null }
}

/** 一条批量帧：写动作 + 批次身份（形状与 handlers 下发的一致） */
function batchStep(callId: string, batchId: string, batchIndex: number) {
  return { ...writeReq(callId), batchId, batchIndex }
}

beforeEach(() => {
  vi.clearAllMocks()
  mockExec.started.length = 0
  mockExec.pending.clear()
  useCopilot.getState().reset()
  // 宿主端口必须注入：没挂载宿主时 store 会在调执行器**之前**就落 executor_error
  setUiToolPorts({
    navigate: vi.fn(),
    currentPath: vi.fn(() => '/'),
    toast: vi.fn(),
    dispatch: vi.fn(),
    openCopilot: vi.fn(),
  })
  vi.mocked(copilotApi.submitUiActionResult).mockResolvedValue({ accepted: true, success: true })
})

describe('store: 写动作互斥', () => {
  it('两条 confirm：第二条在第一条结算之前不开始，结算后依次完成', async () => {
    const store = useCopilot.getState()
    void store.runUiAction(writeReq('seq-1'))
    void store.runUiAction(writeReq('seq-2'))

    await until(() => mockExec.started.length === 1, '第 1 条开始执行')
    expect(mockExec.started).toEqual(['seq-1'])
    // 第 2 条连运行记录都没有：它卡在写锁上，根本没进 runOne
    expect(useCopilot.getState().uiToolRuns['seq-2']).toBeUndefined()

    settle('seq-1', { ok: true })
    await until(() => mockExec.started.length === 2, '第 2 条开始执行')
    expect(mockExec.started).toEqual(['seq-1', 'seq-2'])

    settle('seq-2', { ok: true })
    await until(() => stateOf('seq-2') === 'ok', '第 2 条落 ok')
    expect(runOf('seq-1')).toMatchObject({ state: 'ok' })
  })

  it('safe 动作在 confirm 在飞时照常立即执行（不被写锁串行）', async () => {
    const store = useCopilot.getState()
    void store.runUiAction(writeReq('fly-1'))
    await until(() => mockExec.started.length === 1, '写动作开始执行')

    void store.runUiAction(safeReq('fly-nav'))
    await until(() => mockExec.started.length === 2, 'safe 动作没等写锁就开始了')
    expect(mockExec.started).toEqual(['fly-1', 'fly-nav'])

    // safe 动作能先落 ok，而写动作还在飞：串行会把这一秒变成「点了没反应」
    settle('fly-nav', { ok: true })
    await until(() => stateOf('fly-nav') === 'ok', 'safe 动作落 ok')
    expect(stateOf('fly-1')).toBe('running')

    settle('fly-1', { ok: true })
    await until(() => stateOf('fly-1') === 'ok', '写动作落 ok')
  })

  it('第一条失败不影响第二条：写锁释放，不做「失败即中止」', async () => {
    const store = useCopilot.getState()
    void store.runUiAction(writeReq('retry-1'))
    void store.runUiAction(writeReq('retry-2'))

    await until(() => mockExec.started.length === 1, '第 1 条开始执行')
    settle('retry-1', { ok: false, code: 'executor_error', message: '写库失败' })
    await until(() => mockExec.started.length === 2, '第 2 条照常开始')
    expect(runOf('retry-1')).toMatchObject({ state: 'error', code: 'executor_error' })
    expect(stateOf('retry-2')).toBe('running')

    settle('retry-2', { ok: true })
    await until(() => stateOf('retry-2') === 'ok', '第 2 条落 ok')
  })

  it('超过排队上限的那一条不执行，并回 executor_error 回执', async () => {
    const store = useCopilot.getState()
    // 1 条在飞 + 3 条排队 = 上限；第 5 条必须被挡在门外
    for (const n of [1, 2, 3, 4, 5]) void store.runUiAction(writeReq(`cap-${n}`))

    await until(() => stateOf('cap-5') === 'error', '超限那条落失败')
    expect(runOf('cap-5')).toMatchObject({ state: 'error', code: 'executor_error' })
    expect(ackOf('cap-5')).toMatchObject({
      outcome: 'error',
      code: 'executor_error',
      detail: '写动作太多，排队超限，这一步没有执行',
    })
    expect(mockExec.started).toEqual(['cap-1'])

    // 队里的几条不是被丢掉：前一条结算后照样依次执行
    for (const n of [1, 2, 3, 4]) {
      await until(() => stateOf(`cap-${n}`) === 'running', `cap-${n} 开始执行`)
      settle(`cap-${n}`, { ok: true })
      await until(() => stateOf(`cap-${n}`) === 'ok', `cap-${n} 落 ok`)
    }
    expect(mockExec.started).toEqual(['cap-1', 'cap-2', 'cap-3', 'cap-4'])
  })

  it('「停下」之后排队中的写动作一律 aborted，执行器一次都没跑', async () => {
    const store = useCopilot.getState()
    void store.runUiAction(writeReq('halt-1'))
    void store.runUiAction(writeReq('halt-2'))
    void store.runUiAction(writeReq('halt-3'))

    await until(() => mockExec.started.length === 1, '第 1 条开始执行')
    useCopilot.getState().abortUiActions()
    // 已发出的不追回（软打断只挡后续动作），它照常结算
    settle('halt-1', { ok: true })
    await until(() => stateOf('halt-3') === 'aborted', '排队中的第 3 条也按打断处理')

    expect(mockExec.started).toEqual(['halt-1'])
    expect(runOf('halt-2')).toMatchObject({ state: 'aborted', code: 'aborted' })
    expect(ackOf('halt-2')).toMatchObject({ outcome: 'aborted' })
    expect(ackOf('halt-3')).toMatchObject({ outcome: 'aborted' })
  })

  it('同一批两步写动作：先批次闸门、后写锁，按序完成（两把锁不死等）', async () => {
    const store = useCopilot.getState()
    void store.runUiAction(batchStep('ord-1', 'wl-batch', 0))
    void store.runUiAction(batchStep('ord-2', 'wl-batch', 1))

    // 取锁顺序固定为「先闸门、后写锁」：写锁的持有者不等待任何闸门，因此不会死等
    await until(() => mockExec.started.length === 1, '第 1 步开始执行')
    expect(mockExec.started).toEqual(['ord-1'])

    settle('ord-1', { ok: true })
    await until(() => mockExec.started.length === 2, '第 2 步开始执行')
    settle('ord-2', { ok: true })
    await until(() => stateOf('ord-2') === 'ok', '第 2 步落 ok')
  })

  it('不同批次的两条写动作也互斥（写锁是唯一覆盖跨批的那道）', async () => {
    const store = useCopilot.getState()
    void store.runUiAction(batchStep('xa-1', 'wl-a', 0))
    void store.runUiAction(batchStep('xb-1', 'wl-b', 0))

    // 两个批次的闸门互不相干，但写锁仍只放行一个
    await until(() => mockExec.started.length === 1, '批次 A 的写动作开始')
    expect(mockExec.started).toEqual(['xa-1'])

    settle('xa-1', { ok: true })
    await until(() => mockExec.started.length === 2, '批次 B 的写动作随后开始')
    settle('xb-1', { ok: true })
    await until(() => stateOf('xb-1') === 'ok', '批次 B 落 ok')
  })

  it('两条 confirm 都结算后锁回到空闲：第三条不等任何东西就执行', async () => {
    const store = useCopilot.getState()
    void store.runUiAction(writeReq('idle-1'))
    void store.runUiAction(writeReq('idle-2'))

    await until(() => mockExec.started.length === 1, '第 1 条开始执行')
    settle('idle-1', { ok: true })
    await until(() => mockExec.started.length === 2, '第 2 条开始执行')
    settle('idle-2', { ok: true })
    await until(() => stateOf('idle-2') === 'ok', '第 2 条落 ok')

    // 前面两条都结算了，队尾已空：第三条不该再等任何人
    void store.runUiAction(writeReq('idle-3'))
    await until(() => mockExec.started.length === 3, '第 3 条直接开始')
    expect(mockExec.started).toEqual(['idle-1', 'idle-2', 'idle-3'])

    settle('idle-3', { ok: true })
    await until(() => stateOf('idle-3') === 'ok', '第 3 条落 ok')
  })
})
