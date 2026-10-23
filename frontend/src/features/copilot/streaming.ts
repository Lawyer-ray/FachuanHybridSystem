/**
 * SSE 流消费器：读 Response.body、切帧、按事件类型分发给 handlers。
 *
 * 从 store.send 中抽出（保持 store 只做状态编排）：帧解析在 domain.ts（纯函数），
 * 这里负责 reader 生命周期与事件路由。事件契约见 types.ts / 后端 chat_service。
 * 循环读到底（done 帧后由服务端关流），调用方无需提前退出。
 */

import { parseSseEvent, takeSseFrames } from './domain'
import type { AgentStreamEvent } from './types'

type ToolCallEvent = Extract<AgentStreamEvent, { type: 'tool_call' }>
type ToolResultEvent = Extract<AgentStreamEvent, { type: 'tool_result' }>
type ApprovalEvent = Extract<AgentStreamEvent, { type: 'approval_request' }>

export interface StreamHandlers {
  /** 思考增量（不计入正文） */
  onThinking(chunk: string): void
  /** 正文增量 */
  onDelta(chunk: string): void
  onToolCall(event: ToolCallEvent): void
  onToolResult(event: ToolResultEvent): void
  /** usage 事件（pi 精确计数，一轮内多段 assistant 逐次上报） */
  onUsage(outputTokens: number, inputTokens: number): void
  onApproval(event: ApprovalEvent): void
  /** 排队事件：前方名次（1 起，含自己在队列中的位置） */
  onQueued(position: number): void
  /** 首个推进事件（delta/thinking/tool_call/error/done）：清掉排队提示 */
  onProgress(): void
  onError(message: string): void
  onDone(): void
}

/** 消费一条 agent SSE 流，逐帧分发；流读尽或中途异常时返回/抛出。 */
export async function consumeAgentStream(resp: Response, h: StreamHandlers): Promise<void> {
  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const { frames, rest } = takeSseFrames(buffer)
    buffer = rest
    for (const frame of frames) {
      const event = parseSseEvent(frame)
      if (!event) continue
      switch (event.type) {
        case 'thinking':
          h.onProgress()
          h.onThinking(event.content)
          break
        case 'delta':
          h.onProgress()
          h.onDelta(event.content)
          break
        case 'tool_call':
          h.onProgress()
          h.onToolCall(event)
          break
        case 'tool_result':
          h.onToolResult(event)
          break
        case 'usage':
          h.onUsage(event.output_tokens, event.input_tokens ?? 0)
          break
        case 'approval_request':
          h.onApproval(event)
          break
        case 'activity':
          // queued 时带 position（前方名次）；thinking 不入转录
          if (event.status === 'queued' && typeof event.position === 'number') {
            h.onQueued(event.position)
          }
          break
        case 'error':
          h.onProgress()
          h.onError(event.message)
          break
        case 'done':
          h.onProgress()
          h.onDone()
          break
        default:
          break // meta / activity(thinking) 不入转录
      }
    }
  }
}
