/**
 * `/api/v1/agent` 的**端点收发形状**（请求参数与回执）。
 *
 * 从这里拆出来的原因只有一个：本域契约文件 `types.ts` 恰好顶到 eslint
 * `max-lines: 450` 硬门禁，再加一个类型就挂红。原先按后端资源（usage / stats /
 * compact / tasks / attachments / approvals / questions）就能切干净的那一段
 * 本来就得单独成节，挪出来正好。
 *
 * 留在 `types.ts` 的是**转录与视图模型**（会话、气泡、回合统计、拖拽引用），
 * 两类东西的生命周期不同：回执用完即弃，转录模型要进 store 长期存活。
 *
 * 消费方一律仍从 `@/features/copilot/types` 取（`types.ts` re-export 本文件），
 * 新增类型时先判断它是「回执」还是「模型」，别两边各抄一份。
 */

import type { QuestionItem } from './domain/question'

/** 待审批的高危工具调用（approval_request 事件 → 审批卡） */
export interface PendingApproval {
  approvalId: string
  toolName: string
  toolArgs: Record<string, unknown>
  message: string
  receivedAt: number
  /** 风险等级（low/medium/high/critical） */
  riskLevel?: string
  /** 紧急级：同意前需二次确认 */
  needsSecondConfirmation?: boolean
  /**
   * 哪一栏提的（`approval_request.agent` 原文）。空串 = 没有栏归属（单栏 / 旧后端），
   * 卡片据此不渲染栏标签；多栏轮次才记，见 turn-handlers.onApproval。
   */
  agent?: string
  /** 该栏的 run_id（`approval_request.run_id` 原文；空串 = 旧后端未带） */
  runId?: string
  /** 离线待审（从 GET /approvals/pending 拉回，多来自后台任务），倒计时口径不同 */
  offline?: boolean
  /**
   * 这张卡属于哪个会话。
   *
   * 补拉端点返回的是「当前律师全部会话」的待审项，入队时必须带上归属，
   * 否则 A 会话挂起的高危审批会渲染在 B 会话上（律师以为自己在批 B 的事，
   * 实际放行的是 A 的操作）。与 `PendingQuestion.sessionId` 同口径。
   */
  sessionId?: string
  /** 本地已提交决定后的终态展示 */
  decided?: 'approved' | 'rejected'
}

/**
 * 待回答的结构化提问（`question_request` 事件 → 问答卡；从 /questions/pending 补拉）
 *
 * 与审批**刻意同层但不同语义**：审批是闸门（超时=拒绝，fail-closed），
 * 提问是求助（超时=模型按假设继续，不阻断）。所以这里没有 expired 决断，
 * 只有「已继续但可补答」这一态——`continued`。
 */
export interface PendingQuestion {
  questionId: string
  /**
   * 提问所属会话。
   *
   * **必填才有防串会话的能力**：`question_request` 事件本身不带 session（它只
   * 在某个会话的 SSE 流上出现），所以入队时由 store 补当前 sessionId；
   * `GET /questions/pending` 则自带 `session_id`。缺这个字段，A 会话的提问会
   * 渲染在 B 会话上（红队审查 F11）。
   */
  sessionId: string
  questions: QuestionItem[]
  /** 后端等待窗口（秒）：到点模型按假设继续，但问题不失效 */
  timeoutSeconds: number
  /** 本地收到时刻（倒计时起点，与服务端发事件时刻近似） */
  receivedAt: number
  /** 多答时哪一栏问的（事件 `agent`；缺失 = 主栏/单栏） */
  agentKind?: string
  /** 提交终态：已答 / 已跳过（终态后卡片只读回显） */
  submitted?: 'answered' | 'skipped'
  /** 回答被服务端记录但等待方已超时（`accepted && !success`）：本轮已继续 */
  continued?: boolean
  /** 服务端回执里给律师看的一句话（如「回答已记录，但本轮对话已按超时继续」） */
  note?: string
  /** 提交在途（按钮置忙，防重复提交） */
  submitting?: boolean
}

/** GET /agent/questions/pending 的列表项 */
export interface PendingQuestionItem {
  question_id: string
  session_id: string
  questions: Record<string, unknown>[]
  created_at: string
}

/** POST /agent/question/{id}/answer 的回执 */
export interface QuestionAnswerReceipt {
  success: boolean
  accepted?: boolean
  note?: string
  error?: string
}

/** POST /agent/tasks 的受理回执 */
export interface AgentTaskReceipt {
  session_id: string
  task_id: string
  task_state: string
  title: string
}

/** POST /agent/sessions/{id}/attachments 的上传回执：消息里以 attachment_id 引用 */
export interface AgentAttachmentReceipt {
  attachment_id: string
  filename: string
  size: number
  mime: string
  /** 引用型（拖拽绑定目录树文件）才有：指向绑定文件夹原文件，不复制字节 */
  ref_owner_kind?: 'contract' | 'case'
  ref_contract_id?: number | null
  ref_subpath?: string
}


/** GET /agent/usage 的汇总（token 由 pi 上报，取消/出错轮次也计入） */
export interface UsageSummary {
  runs: number
  ok_runs: number
  error_runs: number
  cancelled_runs: number
  input_tokens: number
  output_tokens: number
  total_tokens: number
  tool_calls: number
  avg_duration_ms: number
  /** 小数（0.05 = 5%） */
  error_rate: number
}

/** GET /agent/approvals/pending 的列表项（离线审批入口） */
export interface PendingApprovalItem {
  approval_id: string
  session_id: string
  tool_name: string
  tool_args: Record<string, unknown>
  risk_level: string
  created_at: string
}

/** GET /agent/sessions/{id}/stats：token 用量与上下文水位（水位未知为 null） */
export interface AgentSessionStats {
  output_tokens: number
  input_tokens: number
  cache_read_tokens: number
  cache_write_tokens: number
  context_used_tokens: number | null
  context_total_tokens: number | null
  context_percent: number | null
}

/** POST /agent/sessions/{id}/compact 的回执（compacted=false 表示未超水位、无事发生） */
export interface AgentCompactReceipt {
  compacted: boolean
  context_used_tokens: number | null
  context_total_tokens: number | null
}

/**
 * GET /agent/ui-actions 的列表行：一次 UI 动作的审计投影（新 → 旧）。
 *
 * 只含 `confirm` / `guarded` 档（`safe` 的只读动作不入库），也只含**当前律师
 * 自己**的行。字段口径与后端 `audit_query.list_recent_for_user` 一一对应；
 * 时间字段是 ISO 8601 字符串，无值时为空串；`verified` 保持三态（`null` = 无法核实）。
 */
export interface UiActionHistoryItem {
  session_id: string
  action: string
  risk: string
  /** `ok` / `error` / `denied` / `aborted` / `expired` / `unknown`（展示口径见 domain/ui-action-history） */
  outcome: string
  /** `approved` / `denied` / `expired`；空串 = 没有审批判定 */
  decision: string
  decided_at: string
  /** 服务端核实：true 真成功 / false 页面报成功但库里没变 / null 无法核实 */
  verified: boolean | null
  verify_note: string
  approved_by_name: string
  created_at: string
  observed_location: string
}

/** GET /agent/ui-actions 的响应体（`count` = 本次返回条数） */
export interface UiActionHistoryResponse {
  items: UiActionHistoryItem[]
  count: number
}
