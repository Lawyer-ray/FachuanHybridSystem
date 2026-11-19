/**
 * SSE 流消费器：读 Response.body、切帧、按事件类型分发给 handlers。
 *
 * 从 store.send 中抽出（保持 store 只做状态编排）：帧解析在 domain.ts（纯函数），
 * 这里负责 reader 生命周期与事件路由。事件契约见 types.ts / 后端 chat_service。
 * 循环读到底（done 帧后由服务端关流），调用方无需提前退出。
 */

import { agentOf, parseSseEvent, runIdOf, takeSseFrames } from './domain'
import type { AgentStreamEvent } from './types'

type ToolCallEvent = Extract<AgentStreamEvent, { type: 'tool_call' }>
type ToolResultEvent = Extract<AgentStreamEvent, { type: 'tool_result' }>
type ApprovalEvent = Extract<AgentStreamEvent, { type: 'approval_request' }>
type QuestionEvent = Extract<AgentStreamEvent, { type: 'question_request' }>

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

/**
 * 「这一帧是谁产的」——多答时前端靠它把交错的事件分到各自的栏。
 *
 * 为什么带在**每个** handler 上而不是进 `StreamHandlers` 的构造参数：一帧只在
 * 帧解析那一刻知道自己的 `agent`，而 handler 是跨帧复用的。带参数的形状让
 * 「事件来自哪个 agent」跟着事件走，不会因为 handler 内部记状态而在交错流里
 * 串栏（两个 agent 的事件是交替到达的，状态一旦落到闭包里就会互相覆盖）。
 */
export interface EventOrigin {
  /** 事件里的 `agent`；缺失时按 pi（见 domain/dual.agentOf） */
  kind: string
  runId: string
}

export interface StreamHandlers {
  /** 思考增量（不计入正文） */
  onThinking(chunk: string, origin: EventOrigin): void
  /** 正文增量 */
  onDelta(chunk: string, origin: EventOrigin): void
  onToolCall(event: ToolCallEvent, origin: EventOrigin): void
  onToolResult(event: ToolResultEvent, origin: EventOrigin): void
  /** usage 事件（pi 精确计数，一轮内多段 assistant 逐次上报）
   *
   * 传结构体而不是位置参数：字段还会长（cache 已是第三个维度），
   * 位置参数每加一个就要改所有实现，且容易错位。
   */
  onUsage(usage: UsagePayload, origin: EventOrigin): void
  /**
   * 审批请求。
   *
   * `origin` 不可省：多答时两栏可能同时要审批，卡上不写来源，律师根本分不清
   * 「这是哪条回答要用我的库表」。单栏时 origin.kind 为空串，渲染按旧口径。
   */
  onApproval(event: ApprovalEvent, origin: EventOrigin): void
  /**
   * 模型反问（结构化提问）。
   *
   * 可选实现，但**不实现就等于把提问丢掉**：后端会阻塞等 180s，然后按假设
   * 继续——法律场景里那等于「AI 自己编了个事实接着干」。所以真正开流的 store
   * 必须实现它。`questions` 是后端归一化后的自由形状（字段见
   * services/question.py），由 domain/question.normalizeQuestions 宽容解析。
   */
  onQuestion?(event: QuestionEvent, origin: EventOrigin): void
  /** 排队事件：前方名次（1 起，含自己在队列中的位置） */
  onQueued(position: number): void
  /** 上下文压缩进行/完成（自动压缩原本无声，律师会以为 AI「失忆」） */
  onCompaction(phase: 'start' | 'end'): void
  /** 首个推进事件（delta/thinking/tool_call/error/done）：清掉排队提示 */
  onProgress(): void
  /**
   * 后端降级：本轮只跑了主后端（aux 席位已满），`reason` 是给律师看的一句话。
   *
   * 可选实现：不关心降级的调用方（测试替身、单后端路径）不必提供。不提供的话，
   * 被丢下的那几栏会一直留在 streaming 状态（光标转不停、done 永远不来），所以
   * 真正开多栏的 store 必须实现它。
   */
  onDegraded?(reason: string): void
  onError(message: string, origin: EventOrigin): void
  /**
   * 某一方跑完。
   *
   * `origin` 不可省：双答时两个后端**各自**发 done（后端保证整轮只有一个
   * done 事件，但那是「会话级」的；每栏仍需要知道「我这栏跑完了」）。
   * 不收 origin 的话，先完成的那栏会让 `finishAssistant()` 把另一栏一起收掉
   * ——另一栏后续的 delta 无处可去，界面上就是「(无内容)」。
   */
  onDone(context: { used: number | null; total: number | null } | undefined, origin: EventOrigin): void
}

/**
 * 流的收尾结论。
 *
 * `sawDone=false` 是**可观测的异常**：连接被掐断时 `reader.read()` 只会正常
 * 返回 `done:true`，看上去和「服务端跑完了」一模一样——不区分就会把断流记成
 * 正常完成（红队审查 R1）。
 */
export interface StreamOutcome {
  /** 是否收到过 done 帧（每栏各发一条，多答时 ≥1 即算正常收尾） */
  sawDone: boolean
}

/** 消费一条 agent SSE 流，逐帧分发；流读尽或中途异常时返回/抛出。 */
export async function consumeAgentStream(resp: Response, h: StreamHandlers): Promise<StreamOutcome> {
  const reader = resp.body!.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let sawDone = false
  for (;;) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const { frames, rest } = takeSseFrames(buffer)
    buffer = rest
    for (const frame of frames) {
      const event = parseSseEvent(frame)
      if (!event) continue
      // 每帧自己的来源：双答时两个 agent 的事件交替到达，绝不能记在 handler 上
      const origin: EventOrigin = { kind: agentOf(event), runId: runIdOf(event) }
      switch (event.type) {
        case 'thinking':
          h.onProgress()
          h.onThinking(event.content, origin)
          break
        case 'delta':
          h.onProgress()
          h.onDelta(event.content, origin)
          break
        case 'tool_call':
          h.onProgress()
          h.onToolCall(event, origin)
          break
        case 'tool_result':
          h.onToolResult(event, origin)
          break
        case 'usage':
          // origin 必须跟着走：多答要按栏归集，丢了来源就只能全算在主栏上
          h.onUsage(
            {
              outputTokens: event.output_tokens,
              inputTokens: event.input_tokens ?? 0,
              cacheReadTokens: event.cache_read_tokens ?? 0,
              cacheWriteTokens: event.cache_write_tokens ?? 0,
            },
            origin,
          )
          break
        case 'approval_request':
          h.onApproval(event, origin)
          break
        case 'question_request':
          // 提问不阻断流：卡片与审批同层并列渲染，模型在服务端等回答
          // （超时即按假设继续，前端仍可补答）
          h.onProgress()
          h.onQuestion?.(event, origin)
          break
        case 'compaction':
          h.onCompaction(event.phase)
          break
        case 'activity':
          // queued 时带 position（前方名次）；thinking 不入转录；
          // degraded 表示多答被降级成只跑主后端（aux 席位已满）
          if (event.status === 'queued' && typeof event.position === 'number') {
            h.onQueued(event.position)
          } else if (event.status === 'degraded') {
            h.onDegraded?.(event.reason ?? '本轮只跑了主后端')
          }
          break
        case 'error':
          // 每个失败方只发一条（后端保证不堆两条），这里按来源挂到对应栏
          h.onProgress()
          h.onError(event.message, origin)
          break
        case 'done':
          sawDone = true
          h.onProgress()
          // 水位字段可选：旧后端 / pi 未上报时 undefined，前端隐藏水位显示
          h.onDone(
            event.context_used_tokens === undefined && event.context_total_tokens === undefined
              ? undefined
              : { used: event.context_used_tokens ?? null, total: event.context_total_tokens ?? null },
            origin,
          )
          break
        default:
          break // meta / activity(thinking) 不入转录
      }
    }
  }

  // 尾帧：服务端关流前可能留下一个没有空行结尾的完整帧（半帧另当别论）。
  // 直接丢掉的话，恰好落在尾巴上的 done 会被当成「没收到」。
  const tail = buffer.trim()
  if (tail.startsWith('data:')) {
    const event = parseSseEvent(tail)
    if (event?.type === 'done') {
      sawDone = true
      h.onProgress()
      h.onDone(
        event.context_used_tokens === undefined && event.context_total_tokens === undefined
          ? undefined
          : { used: event.context_used_tokens ?? null, total: event.context_total_tokens ?? null },
        { kind: agentOf(event), runId: runIdOf(event) },
      )
    }
  }

  return { sawDone }
}
