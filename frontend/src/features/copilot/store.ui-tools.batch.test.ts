/**
 * store 的批量执行语义（node）：同批串行 / 失败即中止 / 跨批不阻塞 / 「停下」收尾。
 *
 * ## 为什么这里替身执行器（别的 store 测试都走真链路）
 *
 * 要证明「前一条没结算，后一条不许开始」，就必须让执行停在半路；真执行器是毫秒级的同步
 * 动作，串行与并发在断言上长得一模一样（两者都会「瞬间跑完」）。所以这里把 `runUiTool`
 * 换成受控 Promise：谁先开始、谁还在等，全看得到。清单漂移仍由 `store.ui-tools.test.ts`
 * 与 `ui-action.e2e.dom.test.tsx` 用真链路守住。
 *
 * ## 断言的都是**执行顺序**
 *
 * 审批卡上写的是「将按顺序执行」。同批真并发了，页面上的结果就与卡片上的承诺不一致——
 * 而这件事不会报错、不会红，只会让律师「先切了 stage 又回到首页」。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'
import { setUiToolPorts } from './store/ui-tools'
import type { UiToolOutcome } from './ui-tools'
import type { UiToolRun } from './state-types'

/**
 * 受控执行器：`started` 记录**开始执行**的顺序，`pending` 让每条停在半路等测试结算。
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
  ],
  validateArgs: () => true,
  runUiTool: (req: { callId: string; args: Record<string, unknown> }) => {
    mockExec.started.push(String(req.args.path))
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
  // 结算回执：中止的步骤也必须发（不发，后端只能等到超时）
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

/** 某个 callId 的后端回执结局（没发过返回 undefined） */
function ackOutcome(callId: string): string | undefined {
  const payloads = vi.mocked(copilotApi.submitUiActionResult).mock.calls.map(([payload]) => payload)
  for (let i = payloads.length - 1; i >= 0; i -= 1) {
    if (payloads[i]?.call_id === callId) return payloads[i]?.outcome
  }
  return undefined
}

/** 一条批量帧：批次 id + 序号 + 目标路径 */
function stepReq(batchId: string | null, callId: string, path: string, batchIndex = 0) {
  return { callId, action: 'ui_navigate', args: { path }, route: null, batchId, batchIndex }
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

describe('store: 批量动作', () => {
  it('同一批三帧按 batch_index 串行执行（前一条没结算，后一条不许开始）', async () => {
    const store = useCopilot.getState()
    const batch = 'batch-order'
    void store.runUiAction(stepReq(batch, 'ord-1', '/a', 0))
    void store.runUiAction(stepReq(batch, 'ord-2', '/b', 1))
    void store.runUiAction(stepReq(batch, 'ord-3', '/c', 2))

    await until(() => mockExec.started.length === 1, '第 1 步开始')
    expect(mockExec.started).toEqual(['/a'])
    expect(useCopilot.getState().uiToolRuns['ord-2']).toBeUndefined()

    settle('ord-1', { ok: true })
    await until(() => mockExec.started.length === 2, '第 2 步开始')
    expect(mockExec.started).toEqual(['/a', '/b'])
    // 批次身份进了运行记录：排障时能看出「这几步是一批的第几步」
    expect(runOf('ord-1')).toMatchObject({ batchId: batch, batchIndex: 0 })

    settle('ord-2', { ok: true })
    await until(() => mockExec.started.length === 3, '第 3 步开始')
    settle('ord-3', { ok: true })
    await until(() => stateOf('ord-3') === 'ok', '第 3 步落 ok')

    expect(mockExec.started).toEqual(['/a', '/b', '/c'])
    expect([runOf('ord-1').batchIndex, runOf('ord-2').batchIndex, runOf('ord-3').batchIndex]).toEqual([0, 1, 2])
  })

  it('第二条失败 → 第三条不执行，标 aborted 并回执', async () => {
    const store = useCopilot.getState()
    const batch = 'batch-fail'
    void store.runUiAction(stepReq(batch, 'fail-1', '/a', 0))
    void store.runUiAction(stepReq(batch, 'fail-2', '/b', 1))
    void store.runUiAction(stepReq(batch, 'fail-3', '/c', 2))

    await until(() => mockExec.started.length === 1, '第 1 步开始')
    settle('fail-1', { ok: true })
    await until(() => mockExec.started.length === 2, '第 2 步开始')
    settle('fail-2', { ok: false, code: 'executor_error', message: '页面炸了' })
    await until(() => stateOf('fail-3') === 'aborted', '第 3 步被标 aborted')

    expect(mockExec.started).toEqual(['/a', '/b']) // 第 3 步一次都没跑
    expect(runOf('fail-2')).toMatchObject({ state: 'error', code: 'executor_error' })
    expect(ackOutcome('fail-3')).toBe('aborted')
  })

  it('不同批次互不阻塞：A 还在跑时 B 的第一步照常开始', async () => {
    const store = useCopilot.getState()
    void store.runUiAction(stepReq('batch-a', 'xa-1', '/a1', 0))
    void store.runUiAction(stepReq('batch-a', 'xa-2', '/a2', 1))
    void store.runUiAction(stepReq('batch-b', 'xb-1', '/b1', 0))

    await until(() => mockExec.started.length === 2, '两个批次各开始一步')
    expect(mockExec.started).toEqual(['/a1', '/b1']) // A 的第 2 步在排队，B 没被牵连

    settle('xa-1', { ok: true })
    await until(() => mockExec.started.length === 3, 'A 的第 2 步开始')
    expect(mockExec.started).toEqual(['/a1', '/b1', '/a2'])

    settle('xa-2', { ok: true })
    settle('xb-1', { ok: true })
    await until(() => stateOf('xa-2') === 'ok' && stateOf('xb-1') === 'ok', '两个批次都落 ok')
  })

  it('「停下」之后同批剩余步骤全部 aborted 并回执', async () => {
    const store = useCopilot.getState()
    const batch = 'batch-stop'
    void store.runUiAction(stepReq(batch, 'stop-1', '/a', 0))
    void store.runUiAction(stepReq(batch, 'stop-2', '/b', 1))
    void store.runUiAction(stepReq(batch, 'stop-3', '/c', 2))

    await until(() => mockExec.started.length === 1, '第 1 步开始')
    useCopilot.getState().abortUiActions()
    // 已发出的不追回（软打断只挡后续动作），它照常结算
    settle('stop-1', { ok: true })
    await until(() => stateOf('stop-3') === 'aborted', '第 3 步被标 aborted')

    expect(mockExec.started).toEqual(['/a'])
    expect(runOf('stop-2')).toMatchObject({ state: 'aborted', code: 'aborted' })
    expect(runOf('stop-3')).toMatchObject({ state: 'aborted', code: 'aborted' })
    expect(ackOutcome('stop-2')).toBe('aborted')
    expect(ackOutcome('stop-3')).toBe('aborted')
  })
})
