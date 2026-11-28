/**
 * `ui_snapshot_request` 帧的分发 + 页面状态应答（node 环境）。
 *
 * ## 为什么这个小文件必须存在
 *
 * 上一轮踩过的坑（2026-11-27 红队评审 P0-1）：只加了 handler 工厂、忘了 `streaming.ts`
 * 里 `switch (event.type)` 的 case，帧落进 `default: break` 被静默丢弃，而编译期不报错
 * （`turn-handlers.ts` 用展开合并，TS 的 excess-property 检查对 spread 不生效）。所以这里
 * 钉的是**真实分发路径**：喂一帧 `ui_snapshot_request`，断言回调被调用、载荷原样到达。
 *
 * 另外几条是应答本身的红线：
 * - 页面**声明了**状态 → 原样回 `state + route`；
 * - 页面**没声明** → 回 `note`（后端转成 `no_page_state`），**不许**把 `{}` 当空页面；
 * - `blocked_actions` 恒发（有声明 = 那份清单、没声明 = 空数组）：模型靠它区分「页面没实现」
 *   与「有但此刻不可用」，不发就等于让它去编一个 `packId` 硬调；
 * - `private_state` 与 `state` **不会混**：它恒发（有声明 = 那份、没声明 = `{}`），但只进日志、
 *   不进模型上下文；handler 把两半接反了就等于把律师没提交的草稿交给了模型，而不会有任何报错。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { submitUiPageSnapshot } from './api'
import { createUiSnapshotHandler } from './handlers/ui-action-handler'
import { consumeAgentStream } from './streaming'
import type { StreamHandlers } from './streaming'
import {
  clearPageBlockedActions,
  clearPagePrivateState,
  readPageState,
  registerPageState,
  setPageBlockedActions,
  setPagePrivateState,
  unregisterPageState,
} from './ui-tools/page-state'

vi.mock('./api', () => ({ submitUiPageSnapshot: vi.fn() }))

/** 把若干 SSE 帧拼成一个一次性 Response（服务端就是这么发的） */
function sseResponse(frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      const encoder = new TextEncoder()
      for (const frame of frames) controller.enqueue(encoder.encode(frame))
      controller.close()
    },
  })
  return new Response(body)
}

/** 最小 handlers：只需要实现被断言的那几个，其余给空实现 */
function handlers(overrides: Partial<StreamHandlers> = {}): StreamHandlers {
  return {
    onThinking: vi.fn(),
    onDelta: vi.fn(),
    onToolCall: vi.fn(),
    onToolResult: vi.fn(),
    onUsage: vi.fn(),
    onApproval: vi.fn(),
    onQueued: vi.fn(),
    onCompaction: vi.fn(),
    onProgress: vi.fn(),
    onError: vi.fn(),
    onDone: vi.fn(),
    ...overrides,
  } as StreamHandlers
}

/** 一帧快照请求（与后端 `UiSnapshotRequestEvent` 逐字段一致） */
const FRAME = { type: 'ui_snapshot_request', request_id: 'r-1', page: 'material-prep', timeout_seconds: 3 } as const
const ORIGIN = { kind: 'pi', runId: '' }

/** 发出去的那次应答（缺了直接给可读失败信息，而不是让断言在 undefined 上炸） */
function sentReply(index = 0) {
  const call = vi.mocked(submitUiPageSnapshot).mock.calls[index]
  if (!call) throw new Error(`没有第 ${index + 1} 次应答：submitUiPageSnapshot 没被调用`)
  return call
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(submitUiPageSnapshot).mockResolvedValue({ accepted: true, success: true })
})

describe('ui_snapshot_request 帧必须真的分发到 onUiSnapshotRequest', () => {
  it('载荷原样到达、origin 回落 pi、清掉排队提示', async () => {
    const onUiSnapshotRequest = vi.fn()
    const h = handlers({ onUiSnapshotRequest })

    await consumeAgentStream(
      sseResponse([
        `data: ${JSON.stringify(FRAME)}\n\n`,
        'data: {"type":"done","session_id":"s-1"}\n\n',
      ]),
      h,
    )

    expect(onUiSnapshotRequest).toHaveBeenCalledTimes(1)
    const [event, origin] = onUiSnapshotRequest.mock.calls[0] as [Record<string, unknown>, { kind: string }]
    expect(event).toMatchObject(FRAME)
    expect(origin.kind).toBe('pi')
    expect(h.onProgress).toHaveBeenCalled()
  })

  it('不实现 onUiSnapshotRequest 时不炸（旧调用方兼容）', async () => {
    const outcome = await consumeAgentStream(
      sseResponse([`data: ${JSON.stringify(FRAME)}\n\n`, 'data: {"type":"done","session_id":"s-1"}\n\n']),
      handlers(),
    )
    expect(outcome.sawDone).toBe(true)
  })
})

describe('页面状态应答', () => {
  it('页面声明了状态：原样回 state + route，不带 note', () => {
    const provider = () => ({ stage: 'todo', selected: 'm-42' })
    registerPageState('material-prep', provider)

    createUiSnapshotHandler().onUiSnapshotRequest?.(FRAME, ORIGIN)

    expect(sentReply()[0]).toBe('r-1')
    expect(sentReply()[1]).toEqual({
      state: { stage: 'todo', selected: 'm-42' },
      route: expect.any(String),
      // 动作名清单（M4）：这页现在能做什么，模型据此不用试错；这里是名字不是结构，截断安全
      available_actions: expect.any(Array),
      // 页面没登记「做不了什么」= 空数组（不是不带键：模型要能区分「没有」与「没问到」）
      blocked_actions: [],
      // 私有那一半恒发（没登记 = 空对象）：一次应答带两半，不用再维护一条要各自对齐的通道
      private_state: {},
    })
    unregisterPageState('material-prep', provider)
  })

  it('页面登记了私有状态：带在 private_state 里，且**不混进 state**', () => {
    const provider = () => ({ stage: 'todo' })
    const privateState = { draftText: '律师还没提交的草稿', openDetail: '/material-prep/571' }
    registerPageState('material-prep', provider)
    setPagePrivateState('material-prep', privateState)

    createUiSnapshotHandler().onUiSnapshotRequest?.(FRAME, ORIGIN)

    const reply = sentReply()[1]
    expect(reply.private_state).toEqual(privateState)
    // 两半混回去是本条通道最坏的失效形态：它不会报错，只会让模型把草稿当既成事实。
    // 逐个键查，防止以后有人在 handler 里展开合并（`...read`）时把它一并带进 state。
    expect(reply.state).toEqual({ stage: 'todo' })
    for (const key of Object.keys(privateState)) expect(reply.state).not.toHaveProperty(key)

    unregisterPageState('material-prep', provider)
    clearPagePrivateState('material-prep')
  })

  it('页面登记了做不了的动作：blocked_actions 原样带上原因', () => {
    const provider = () => ({ selected: null })
    const blocked = [{ name: 'ui_material_prep_judge', reason: '当前没有选中材料包：先让律师选一条' }]
    registerPageState('material-prep', provider)
    setPageBlockedActions('material-prep', blocked)

    createUiSnapshotHandler().onUiSnapshotRequest?.(FRAME, ORIGIN)

    expect(sentReply()[1]).toMatchObject({ blocked_actions: blocked })
    unregisterPageState('material-prep', provider)
    clearPageBlockedActions('material-prep')
  })

  it('页面没声明状态：回 note，不许把 {} 当成空页面', () => {
    createUiSnapshotHandler().onUiSnapshotRequest?.({ ...FRAME, page: 'never-registered' }, ORIGIN)

    expect(sentReply()[1]).toEqual({
      state: {},
      route: expect.any(String),
      note: '页面没有声明状态',
      // 页面没声明状态 = 不知道它有哪些动作，回空表而不是编一份猜的清单
      available_actions: [],
      blocked_actions: [],
      // 私有那一半同理：不许按当前地址编一份猜的
      private_state: {},
    })
  })

  it('POST 失败只 warn：不 await，也不把异常扔回读循环', async () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    vi.mocked(submitUiPageSnapshot).mockRejectedValueOnce(new Error('网络抖动'))

    createUiSnapshotHandler().onUiSnapshotRequest?.({ ...FRAME, page: 'never-registered' }, ORIGIN)
    await new Promise((resolve) => setTimeout(resolve, 0))

    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})

describe('页面状态注册表（同页多实例）', () => {
  it('注销一个实例后仍能读到另一个；全部注销后才返回 null', () => {
    const first = () => ({ v: 'first' })
    const second = () => ({ v: 'second' })
    registerPageState('material-prep', first)
    registerPageState('material-prep', second)

    // 最近注册的实例优先（同一页同时挂两处时，后挂的那个是「当前」）
    expect(readPageState('material-prep')?.state.v).toBe('second')

    unregisterPageState('material-prep', second)
    expect(readPageState('material-prep')?.state.v).toBe('first')

    unregisterPageState('material-prep', first)
    expect(readPageState('material-prep')).toBeNull()
  })
})
