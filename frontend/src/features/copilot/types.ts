/**
 * Copilot 域类型：/api/v1/agent 的接口契约与前端转录模型。
 * 后端事件契约见 backend/apps/agent/services/chat_service.py 顶部注释。
 */

/** 会话（GET/POST /agent/sessions） */
export interface AgentSession {
  session_id: string
  title: string
  status: string
  /** 最近一轮实际使用的模型（服务端回写；未对话过为空） */
  llm_model: string
  created_at: string
  updated_at: string
}

/** 历史消息（GET /agent/sessions/{id}/messages） */
export interface AgentHistoryMessage {
  message_id: number
  role: 'user' | 'assistant' | 'tool'
  content: string
  tool_name: string
  created_at: string
  metadata: Record<string, unknown>
}

/** SSE 流事件（POST /agent/sessions/{id}/messages 的 data 帧） */
export type AgentStreamEvent =
  | { type: 'meta'; session_id: string; agent?: string }
  | { type: 'activity'; status: string; agent?: string }
  | { type: 'delta'; content: string }
  | { type: 'thinking'; content: string }
  | { type: 'tool_call'; tool_call_id: string; name: string; arguments?: unknown }
  | { type: 'tool_result'; tool_call_id: string; name: string; result?: string }
  | {
      type: 'approval_request'
      approval_id: string
      tool_name: string
      tool_args?: Record<string, unknown>
      message: string
    }
  | { type: 'error'; message: string }
  | { type: 'usage'; output_tokens: number; input_tokens?: number }
  | { type: 'done'; session_id: string }

/** 一轮对话的输出统计（实时估算 + 结束后真实值） */
export interface TurnStats {
  /** 首个 delta 到达时间（ms） */
  firstDeltaAt: number | null
  /** 最近一次 delta 时间（ms），流停后的参考终点 */
  lastDeltaAt: number | null
  /** 流结束时间（ms） */
  doneAt: number | null
  /** 字符启发式累计估算 token */
  estTokens: number
  /** usage 事件的精确累计（未收到为 null） */
  exactTokens: number | null
  /** 采样点 [时间, 累计估算 token]，只保留近几秒 */
  samples: Array<[number, number]>
}

/** 转录气泡（历史回放与流式共用一个模型） */
export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  /** tool 消息的工具名（tool_call 与 tool_result 的归并键） */
  toolName?: string
  toolCallId?: string
  /** 回答被停止/断连截断（服务端 metadata.truncated 透传） */
  truncated?: boolean
  /** 正在流式接收中（assistant 专属） */
  streaming?: boolean
  /** 模型的思考过程（开启思考模式时由 thinking 事件累积，仅展示不入正文） */
  thinking?: string
  /** 思考已完成（收到首个正文 delta 后置位，用于折叠/收起样式） */
  thinkingDone?: boolean
}

/** 待审批的高危工具调用（approval_request 事件 → 审批卡） */
export interface PendingApproval {
  approvalId: string
  toolName: string
  toolArgs: Record<string, unknown>
  message: string
  receivedAt: number
  /** 本地已提交决定后的终态展示 */
  decided?: 'approved' | 'rejected'
}
