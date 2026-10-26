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

/**
 * usage 事件的归一化载荷。
 *
 * `cacheReadTokens` 是验证「提示词前缀稳定 → 命中 prompt cache」的唯一手段：
 * 它高说明前缀没变（记忆快照没漂、工具集没抖）、成本低；它低说明每轮都在
 * 重建前缀。命中率 = cacheRead / (input + cacheRead + cacheWrite)。
 */
export interface UsagePayload {
  outputTokens: number
  inputTokens: number
  cacheReadTokens: number
  cacheWriteTokens: number
}

export interface StreamHandlers {
  /** 思考增量（不计入正文） */
  onThinking(chunk: string): void
  /** 正文增量 */
  onDelta(chunk: string): void
  onToolCall(event: ToolCallEvent): void
  onToolResult(event: ToolResultEvent): void
  /** usage 事件（pi 精确计数，一轮内多段 assistant 逐次上报）
   *
   * 传结构体而不是位置参数：字段还会长（cache 已是第三个维度），
   * 位置参数每加一个就要改所有实现，且容易错位。
   */
  onUsage(usage: UsagePayload): void
  onApproval(event: ApprovalEvent): void
  /** 排队事件：前方名次（1 起，含自己在队列中的位置） */
  onQueued(position: number): void
  /** 上下文压缩进行/完成（自动压缩原本无声，律师会以为 AI「失忆」） */
  onCompaction(phase: 'start' | 'end'): void
  /** 首个推进事件（delta/thinking/tool_call/error/done）：清掉排队提示 */
  onProgress(): void
  onError(message: string): void
  onDone(context?: { used: number | null; total: number | null }): void
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
          h.onUsage({
            outputTokens: event.output_tokens,
            inputTokens: event.input_tokens ?? 0,
            cacheReadTokens: event.cache_read_tokens ?? 0,
            cacheWriteTokens: event.cache_write_tokens ?? 0,
          })
          break
        case 'approval_request':
          h.onApproval(event)
          break
        case 'compaction':
          h.onCompaction(event.phase)
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
          // 水位字段可选：旧后端 / pi 未上报时 undefined，前端隐藏水位显示
          h.onDone(
            event.context_used_tokens === undefined && event.context_total_tokens === undefined
              ? undefined
              : { used: event.context_used_tokens ?? null, total: event.context_total_tokens ?? null },
          )
          break
        default:
          break // meta / activity(thinking) 不入转录
      }
    }
  }
}
