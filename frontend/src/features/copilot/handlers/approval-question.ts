/**
 * 交互类事件：审批卡入列、模型反问入列、排队名次、上下文压缩阶段。
 *
 * 这四个都是「把事件翻译成 store 里的一张卡/一行状态」，与正文无关；也都要补
 * 事件本身不带、只能从当前会话/本轮栏数推出的归属信息（session_id、栏标签）。
 */

import { normalizeQuestions } from '../domain'
import type { StreamHandlers } from '../streaming'
import type { TurnHandlerContext } from './context'

/** 无 `timeout_seconds` 时的兜底等待窗口（与后端 DEFAULT_QUESTION_TIMEOUT_S 同值） */
const QUESTION_TIMEOUT_FALLBACK_S = 180

export function createApprovalQuestionHandlers(
  ctx: TurnHandlerContext,
): Pick<StreamHandlers, 'onApproval' | 'onQuestion' | 'onQueued' | 'onCompaction'> {
  const { set, get, columnCount } = ctx

  const onApproval: StreamHandlers['onApproval'] = (event, origin) => {
    const sessionId = get().sessionId
    // 「哪一栏提的」只在多栏轮次才记：单栏没有第二栏可分，记下来只会在卡上
    // 多一个没有信息量的徽标。
    //
    // 读 `event.agent` 而不是 `origin.kind`：后者缺失时回落到 pi（见
    // domain/dual.agentOf），是为了事件路由而做的归一——拿它当来源会把
    // 「旧后端没带 agent」误标成 pi，正是这张卡要避免的假归属。
    const laneAgent = columnCount > 1 ? event.agent ?? '' : ''
    set((s) => {
      // 同一 approval_id 只留一张（重放/重连可能重复投递）；**不能按
      // tool_name 去重**——两栏同时要删同一张表是合法的两张卡，各自独立决定
      if (s.approvals.some((a) => a.approvalId === event.approval_id)) return s
      return {
        approvals: [
          ...s.approvals,
          {
            approvalId: event.approval_id,
            toolName: event.tool_name,
            toolArgs: event.tool_args ?? {},
            // 契约里 `message` 带默认值 → 线路上可能不发这个键（节点/降级卡片会这样）。
            // 缺失时给空串：卡片正文区留白，但按钮与倒计时照常工作（不能整个卡片不渲染）。
            message: event.message ?? '',
            receivedAt: Date.now(),
            riskLevel: event.risk_level,
            needsSecondConfirmation: event.needs_second_confirmation,
            // 空串 = 单栏 / 旧后端未带：卡片据此不渲染栏标签
            agent: laneAgent,
            runId: origin.runId,
            // 事件只出现在某个会话的流上，入队时补归属：补拉路径拿服务端的
            // `session_id` 过滤，两条路径必须同一个字段才不会再把别人的卡带进来
            ...(sessionId ? { sessionId } : {}),
          },
        ],
      }
    })
  }

  const onQuestion: StreamHandlers['onQuestion'] = (event, origin) => {
    // 归一化失败（模型给了完全无法解析的题面）时宁可不渲染，也不占着交互席位：
    // 后端到点会按假设继续，前端多一张空白卡只会让人以为是 bug
    const questions = normalizeQuestions(event.questions)
    if (questions.length === 0) return
    // 事件不带 session（它只出现在某个会话的流上）：入队时补上，
    // 否则切会话后旧会话的提问会渲染到新会话里
    const sessionId = get().sessionId
    if (!sessionId) return
    get().enqueueQuestion({
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
  }

  const onQueued: StreamHandlers['onQueued'] = (position) => {
    set({ queuePosition: Math.max(1, position) })
  }

  const onCompaction: StreamHandlers['onCompaction'] = (phase) => {
    // start→end 之间 Composer 底栏显示「正在压缩上下文…」；
    // 结束不额外弹提示——水位条本身会随 done 事件下降，那就是最直白的交代
    set({ compacting: phase === 'start' })
  }

  return { onApproval, onQuestion, onQueued, onCompaction }
}
