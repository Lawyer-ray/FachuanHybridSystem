/**
 * 一轮流式对话的 store 更新处理器（从 store.send 抽出，控制单文件规模）。
 *
 * createTurnHandlers 返回 { handlers, finishAssistant }：
 * - handlers 喂给 streaming.consumeAgentStream，把 SSE 事件翻译成 Zustand 状态更新
 *   （正文/思考累积、工具行归并、审批卡入列、排队名次、轮次统计采样）
 * - finishAssistant 收尾助手气泡（流读尽与 done 双路径都要能调，幂等）
 */

import { estimateTokens, extractRewriteArgs, nextLocalId, normalizeQuestions, parseFileRewrite } from './domain'
import { FILE_REWRITTEN_EVENT } from './launch'
import type { EventOrigin, StreamHandlers } from './streaming'
import { useCopilot } from './store'

type CopilotSet = typeof useCopilot.setState

/**
 * `assistantFor`：事件的 agent kind → 该写进哪条 assistant 气泡的 id。
 *
 * 键是 `agent`（`pi` / `dsh`），特殊键 `''` 是兜底（单后端轮次 / 事件缺 agent）。
 * 由 store 在开流时按「本轮有哪些栏」建好，闭包里只读不写。
 */
export type AssistantRoute = (kind: string) => string

export function createTurnHandlers(
  defaultAssistantId: string,
  set: CopilotSet,
  assistantFor: AssistantRoute = () => defaultAssistantId,
  /** 本轮选了几栏（>1 = 多答）。注意它只表达「律师想跑几栏」，
   *  **不能**用来判「事件该怎么路由」——见 targetOf。错误行只在多栏时才标来源：
   *  单后端时多加一个「pi：」前缀会改变律师已经习惯的文案，而它并不带来任何
   *  区分信息。 */
  columnCount = 1,
): {
  handlers: StreamHandlers
  finishAssistant: () => void
} {
  /** rewrite_folder_file 各调用的参数（key = tool_call_id）。
   *
   * 原文/改写全文只在这里完整到达：tool_result 的 result 被 SSE 截到
   * 2000 字，靠它读不回正文。落盘成功时把这对字段带进 file-rewritten
   * 事件，打开中的画布就能就地落修订（免整页重载）。轮结束即随闭包
   * 回收，无跨轮泄漏。 */
  const rewriteArgsById = new Map<string, { original: string; replacement: string }>()

  /** 无 `timeout_seconds` 时的兜底等待窗口（与后端 DEFAULT_QUESTION_TIMEOUT 同值） */
  const QUESTION_TIMEOUT_FALLBACK_S = 180

  /**
   * 这一帧该写进哪条气泡。
   *
   * 多栏时 `origin.kind` 是精确的，但**按栏清单判断，不按 columnCount 判断**：
   * 后端可能降级（aux 席位满 → 只跑主后端并收窄 agents），也可能某个 kind 不在
   * 清单里。这两种情况下 `assistantFor` 会回落到默认气泡——单栏轮次里事件带的
   * `agent` 是后端自己的 kind（`pi` / `dsh` / `openai-agents`），而单栏气泡没有
   * 登记在任何 kind 名下（见 store/turn.ts：只有多栏才建 assistantByAgent）。
   * 一律走 `assistantFor` 让「路由表怎么建的就怎么查」，两处只有一份真相。
   */
  const targetOf = (kind: string): string => assistantFor(kind)

  const appendAssistant = (chunk: string, origin: EventOrigin) => {
    if (!chunk) return
    const targetId = targetOf(origin.kind)
    set((s) => ({
      messages: s.messages.map((m) =>
        // 首个正文 delta 到达 → 思考阶段结束（供前端收起/打勾）
        m.id === targetId ? { ...m, content: m.content + chunk, thinkingDone: true } : m,
      ),
    }))
  }
  const appendThinking = (chunk: string, origin: EventOrigin) => {
    if (!chunk) return
    const targetId = targetOf(origin.kind)
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === targetId ? { ...m, thinking: (m.thinking ?? '') + chunk } : m,
      ),
    }))
  }
  /** 收尾**全部**本轮的 assistant 气泡（多答各栏都要停住光标） */
  const finishAssistant = () => {
    set((s) => ({
      messages: s.messages.map((m) =>
        m.role === 'assistant' && m.streaming ? { ...m, streaming: false } : m,
      ),
    }))
  }
  /** 仅在有值时才 set（避免每个 delta 都触发一次状态写入） */
  const clearQueueBanner = () => {
    set((s) => (s.queuePosition !== null ? { queuePosition: null } : s))
  }

  const handlers: StreamHandlers = {
    onThinking: appendThinking,
    onDelta: (chunk, origin) => {
      appendAssistant(chunk, origin)
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
    onToolCall: (event, origin) => {
      // rewrite_folder_file：参数渐进完整时后一条覆盖前一条（以完整到达为准）
      if (event.tool_call_id && event.name?.endsWith('rewrite_folder_file')) {
        const extracted = extractRewriteArgs(event.arguments)
        if (extracted) rewriteArgsById.set(event.tool_call_id, extracted)
      }
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
              // 多答时各栏各自调工具：工具行必须带来源，否则回放时分不出证据归谁
              ...(origin.kind ? { agentKind: origin.kind } : {}),
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
      // AI 把修订写回文件夹文件（rewrite_folder_file 落盘成功）：广播给正
      // 打开该文件的编辑器画布。带 original/replacement（来自同次调用的参
      // 数）时画布优先**就地落修订**（插件桥），失败或缺参才换 key 重载
      const rewriteArgs = event.tool_call_id ? rewriteArgsById.get(event.tool_call_id) : undefined
      if (event.tool_call_id) rewriteArgsById.delete(event.tool_call_id)
      const rewrite = parseFileRewrite(event.name, String(event.result ?? ''), event.is_error === true, rewriteArgs)
      if (rewrite) {
        window.dispatchEvent(new CustomEvent(FILE_REWRITTEN_EVENT, { detail: rewrite }))
      }
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
    onQuestion: (event, origin) => {
      // 归一化失败（模型给了完全无法解析的题面）时宁可不渲染，也不占着交互席位：
      // 后端到点会按假设继续，前端多一张空白卡只会让人以为是 bug
      const questions = normalizeQuestions(event.questions)
      if (questions.length === 0) return
      // 事件不带 session（它只出现在某个会话的流上）：入队时补上，
      // 否则切会话后旧会话的提问会渲染到新会话里
      const sessionId = useCopilot.getState().sessionId
      if (!sessionId) return
      useCopilot.getState().enqueueQuestion({
        questionId: event.question_id,
        sessionId,
        questions,
        timeoutSeconds:
          typeof event.timeout_seconds === 'number' && event.timeout_seconds > 0
            ? event.timeout_seconds
            : QUESTION_TIMEOUT_FALLBACK_S,
        receivedAt: Date.now(),
        ...(origin.kind ? { agentKind: origin.kind } : {}),
      })
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
    onDegraded: (reason) => {
      // 后端降级（aux 席位已满）：本轮律师选了几家，实际只跑了一家。不说明的话
      // 他会以为对比没生效、或者其余几家的回答丢了。
      //
      // 同时要把**被丢下的那几栏**就地收尾并标「本轮未做」：后端收窄了 agents，
      // 只会给主栏发 done，其余栏永远等不到收尾信号——界面上就是一排转圈的空栏。
      // 主栏是 `assistantFor('')`（路由表为空时它就是第一栏，见 store/turn.ts）。
      const keptId = assistantFor('')
      set((s) => ({
        messages: s.messages.map((m) =>
          m.role === 'assistant' && m.streaming && m.id !== keptId
            ? { ...m, streaming: false, failed: true }
            : m,
        ),
        lastError: reason,
      }))
    },
    onError: (message, origin) => {
      // 多答时一个后端失败其他照常输出：错误行必须标明是哪一栏失败了，
      // 否则律师会以为整轮都没跑成，而屏幕上半截明明有答案。
      const who = columnCount > 1 && origin.kind ? `${origin.kind}：` : ''
      set({ lastError: `${who}${message}` })
      // 失败方的栏要停住光标并标成「本轮未做」；其他栏继续流（finishAssistant
      // 会把所有 streaming 气泡收掉，这里只收失败那一栏）。
      //
      // 为什么明写「本轮未做」而不是留空：那一栏到收尾都没有正文，不标记的话
      // 界面上就是一个空白的栏头，看起来像「AI 回答了但内容丢了」。
      // 查不到时（本轮没登记过该 agent）回落到默认栏，不造孤儿气泡
      const failedId = targetOf(origin.kind)
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === failedId ? { ...m, streaming: false, failed: true } : m,
        ),
      }))
    },
    onDone: (context, origin) => {
      // **只收这一栏**，不能 `finishAssistant()`（那会收掉全部 streaming 气泡）。
      //
      // 多答真实事故：pi 先完成 → done 到达 → 全部气泡被收掉 → dsh 后续的 delta
      // 无处可写，界面上两栏都是「(无内容)」，并冒出一句「流处理异常」。
      // 单后端时 columnCount === 1，收这一栏等价于收全部，行为与原来一致。
      const doneId = targetOf(origin.kind)
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === doneId && m.streaming ? { ...m, streaming: false } : m,
        ),
      }))
      // 整轮是否结束由「还有没有栏在流」决定：多栏时要把 doneAt / 排队清空 /
      // 水位写回推到最后一栏完成；单栏时立即执行（与原来等价）。
      const stillStreaming = useCopilot.getState().messages.some((m) => m.role === 'assistant' && m.streaming)
      if (stillStreaming) {
        // 还有栏没跑完：水位是「本轮最后状态」，留到收尾时再写
        return
      }
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
