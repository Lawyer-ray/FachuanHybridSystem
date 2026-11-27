/**
 * `ui_action` 帧的分发回归（node 环境，直接喂 `consumeAgentStream`）。
 *
 * ## 为什么这个小文件必须存在
 *
 * 2026-11-27 红队评审 P0-1：`createUiActionHandler` 返回的键名是事件名 `ui_action`，而
 * 帧分发是 `streaming.ts` 里一棵写死的 `switch (event.type)`。两侧对不上时**编译不报错**
 * （`turn-handlers.ts` 用展开合并，TS 的 excess-property 检查对 spread 不生效），
 * 于是帧落进 `default: break` 被静默丢弃 —— 模型照旧说"已帮你切过去"，页面一动不动。
 *
 * 所以这里钉的不是 handler 的实现细节，而是**真实分发路径**：喂一帧 `ui_action`，
 * 断言回调被调用、载荷四个字段原样到达、`origin` 按 `agent` 归类。
 */

import { describe, expect, it, vi } from 'vitest'

import { consumeAgentStream } from './streaming'
import type { StreamHandlers } from './streaming'

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

describe('ui_action 帧必须真的分发到 onUiAction', () => {
  it('单栏：载荷四字段原样到达，origin 回落 pi', async () => {
    const onUiAction = vi.fn()
    const h = handlers({ onUiAction })

    await consumeAgentStream(
      sseResponse([
        'data: {"type":"ui_action","call_id":"c1","action":"ui_material_prep_set_stage","arguments":{"stage":"todo"},"route":"/material-prep"}\n\n',
        'data: {"type":"done","session_id":"s-1"}\n\n',
      ]),
      h,
    )

    expect(onUiAction).toHaveBeenCalledTimes(1)
    const [event, origin] = onUiAction.mock.calls[0] as [Record<string, unknown>, { kind: string }]
    expect(event).toMatchObject({
      type: 'ui_action',
      call_id: 'c1',
      action: 'ui_material_prep_set_stage',
      arguments: { stage: 'todo' },
      route: '/material-prep',
    })
    // 没有 agent 字段 → 按 pi 归类（与 domain/dual.agentOf 同口径）
    expect(origin.kind).toBe('pi')
    // 动作属于「有进展」，必须清掉排队提示
    expect(h.onProgress).toHaveBeenCalled()
  })

  it('多栏：origin 带事件自己的 agent，横幅才能标清是哪一栏在动', async () => {
    const onUiAction = vi.fn()
    await consumeAgentStream(
      sseResponse([
        'data: {"type":"ui_action","call_id":"c2","action":"ui_navigate","arguments":{"path":"/projects"},"route":null,"agent":"dsh","run_id":"r-9"}\n\n',
        'data: {"type":"done","session_id":"s-1","agent":"dsh"}\n\n',
      ]),
      handlers({ onUiAction }),
    )
    expect((onUiAction.mock.calls[0] as unknown[])[1]).toMatchObject({ kind: 'dsh', runId: 'r-9' })
  })

  it('不实现 onUiAction 时不炸（旧调用方兼容）', async () => {
    const outcome = await consumeAgentStream(
      sseResponse([
        'data: {"type":"ui_action","call_id":"c3","action":"ui_navigate","arguments":{"path":"/"}}\n\n',
        'data: {"type":"done","session_id":"s-1"}\n\n',
      ]),
      handlers(),
    )
    expect(outcome.sawDone).toBe(true)
  })
})
