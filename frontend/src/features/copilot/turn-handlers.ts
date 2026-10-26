/**
 * 一轮流式对话的 store 更新处理器（从 store.send 抽出，控制单文件规模）。
 *
 * createTurnHandlers 返回 { handlers, finishAssistant }：
 * - handlers 喂给 streaming.consumeAgentStream，把 SSE 事件翻译成 Zustand 状态更新
 *   （正文/思考累积、工具行归并、审批卡入列、排队名次、轮次统计采样）
 * - finishAssistant 收尾助手气泡（流读尽与 done 双路径都要能调，幂等）
 */

import { estimateTokens, nextLocalId } from './domain'
import type { StreamHandlers } from './streaming'
import type { useCopilot } from './store'

type CopilotSet = typeof useCopilot.setState

export function createTurnHandlers(assistantId: string, set: CopilotSet): {
  handlers: StreamHandlers
  finishAssistant: () => void
} {
  const appendAssistant = (chunk: string) => {
    if (!chunk) return
    set((s) => ({
      messages: s.messages.map((m) =>
        // 首个正文 delta 到达 → 思考阶段结束（供前端收起/打勾）
        m.id === assistantId ? { ...m, content: m.content + chunk, thinkingDone: true } : m,
      ),
    }))
  }
  const appendThinking = (chunk: string) => {
    if (!chunk) return
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === assistantId ? { ...m, thinking: (m.thinking ?? '') + chunk } : m,
      ),
    }))
  }
  const finishAssistant = () => {
    set((s) => ({
      messages: s.messages.map((m) => (m.id === assistantId ? { ...m, streaming: false } : m)),
    }))
  }
  /** 仅在有值时才 set（避免每个 delta 都触发一次状态写入） */
  const clearQueueBanner = () => {
    set((s) => (s.queuePosition !== null ? { queuePosition: null } : s))
  }

  const handlers: StreamHandlers = {
    onThinking: appendThinking,
    onDelta: (chunk) => {
      appendAssistant(chunk)
      set((s) => {
        const now = Date.now()
        const estTokens = s.turnStats.estTokens + estimateTokens(chunk)
        const samples = [...s.turnStats.samples, [now, estTokens] as [number, number]]
        // 只留最近 4 秒的采样，窗口计算足够（2s 窗口）
        const cutoff = now - 4000
        const start = samples.findIndex(([t]) => t >= cutoff)
        return {
          turnStats: {
            ...s.turnStats,
            firstDeltaAt: s.turnStats.firstDeltaAt ?? now,
            lastDeltaAt: now,
            estTokens,
            samples: start > 0 ? samples.slice(start) : samples,
          },
        }
      })
    },
    onToolCall: (event) => {
      // pi 对同一工具调用可能发多条 message_end（arguments 渐进完整），
      // 以 tool_call_id 去重：已有则原行保留，没有才追加
      set((s) => {
        if (event.tool_call_id && s.messages.some((m) => m.toolCallId === event.tool_call_id)) {
          return s
        }
        return {
          messages: [
            ...s.messages,
            {
              id: nextLocalId(),
              role: 'tool',
              content: '',
              toolName: event.name,
              toolCallId: event.tool_call_id,
            },
          ],
        }
      })
    },
    onToolResult: (event) => {
      const matchId = event.tool_call_id
      set((s) => ({
        // tool_call 与 tool_result 以 tool_call_id 归并；缺 id 时落最近一个空 tool 气泡
        messages: s.messages.map((m, i) => {
          const byId = m.role === 'tool' && matchId && m.toolCallId === matchId
          const lastEmpty =
            !matchId && m.role === 'tool' && !m.content && s.messages.slice(i + 1).every((x) => x.role !== 'tool')
          return byId || lastEmpty ? { ...m, content: String(event.result ?? '') } : m
        }),
      }))
    },
    onUsage: (usage) => {
      set((s) => ({
        turnStats: {
          ...s.turnStats,
          // exactTokens 只算输出：上一代 UI 用它展示「生成速度」，混进输入
          // 会让速度虚高数倍。输入侧成本看 input/cache 两个字段。
          exactTokens: (s.turnStats.exactTokens ?? 0) + usage.outputTokens,
          inputTokens: (s.turnStats.inputTokens ?? 0) + usage.inputTokens,
          cacheReadTokens: (s.turnStats.cacheReadTokens ?? 0) + usage.cacheReadTokens,
          cacheWriteTokens: (s.turnStats.cacheWriteTokens ?? 0) + usage.cacheWriteTokens,
        },
      }))
    },
    onApproval: (event) => {
      set((s) => ({
        approvals: [
          ...s.approvals,
          {
            approvalId: event.approval_id,
            toolName: event.tool_name,
            toolArgs: event.tool_args ?? {},
            message: event.message,
            receivedAt: Date.now(),
            riskLevel: event.risk_level,
            needsSecondConfirmation: event.needs_second_confirmation,
          },
        ],
      }))
    },
    onQueued: (position) => {
      set({ queuePosition: Math.max(1, position) })
    },
    onCompaction: (phase) => {
      // start→end 之间 Composer 底栏显示「正在压缩上下文…」；
      // 结束不额外弹提示——水位条本身会随 done 事件下降，那就是最直白的交代
      set({ compacting: phase === 'start' })
    },
    onProgress: clearQueueBanner,
    onError: (message) => {
      set({ lastError: message })
      finishAssistant()
    },
    onDone: (context) => {
      finishAssistant()
      set((s) => ({
        turnStats: { ...s.turnStats, doneAt: Date.now() },
        queuedSteers: [],
        // done 带水位才写：不带（旧后端/未上报）保持原值，别把已知水位冲成 null
        ...(context ? { contextUsage: { used: context.used, total: context.total } } : {}),
      }))
    },
  }

  return { handlers, finishAssistant }
}
