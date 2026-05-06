/** 工作台类型定义 */

export interface WorkbenchSession {
  id: number
  session_id: string
  title: string
  llm_model: string
  status: string
  created_at: string
  updated_at: string
}

export interface WorkbenchMessage {
  id: number
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  llm_model: string
  tool_call_id: string
  tool_name: string
  tool_input: Record<string, unknown>
  tool_output: Record<string, unknown>
  metadata: Record<string, unknown>
  created_at: string
}

export interface LLMModel {
  id: string
  name: string
  provider?: string
  context_window?: number
}

export interface ModelsResponse {
  models: LLMModel[]
  default_model: string
  is_fallback: boolean
  error_message: string
}

// ─── Agent 类型 ───────────────────────────────────────────────────────────────

export type AgentType = 'triage' | 'case' | 'contract' | 'research' | 'general'

export interface AgentInfo {
  type: AgentType
  name: string
  description: string
}

export const AGENT_OPTIONS: AgentInfo[] = [
  { type: 'triage', name: '分诊助手', description: '自动判断意图并路由到专业助手' },
  { type: 'case', name: '案件管理', description: '案件创建、查询、修改' },
  { type: 'contract', name: '合同管理', description: '合同查询、下载、生成' },
  { type: 'research', name: '法律检索', description: '案例检索、企业信息查询' },
  { type: 'general', name: '通用助手', description: '其他杂项操作' },
]

// ─── 审批状态 ─────────────────────────────────────────────────────────────────

export interface ApprovalState {
  approvalId: string
  toolName: string
  toolArgs: Record<string, unknown>
}

// ─── 消息分组（用于内联展示工具调用） ────────────────────────────────────────

export interface AssistantMessageGroup {
  assistant: WorkbenchMessage
  toolCalls: WorkbenchMessage[]
}

// ─── SSE 事件 ─────────────────────────────────────────────────────────────────

export interface SSEEvent {
  type: string
  content?: string
  message?: string
  tool_call_id?: string
  name?: string
  tool_name?: string
  arguments?: Record<string, unknown>
  tool_input?: Record<string, unknown>
  result?: unknown
  tool_output?: Record<string, unknown>
  success?: boolean
  approval_id?: string
  session_id?: string
  model?: string
  agent?: string
  status?: string
  from_agent?: string
  to_agent?: string
}

// ─── 流式消息（前端维护） ─────────────────────────────────────────────────────

export interface StreamingMessage {
  role: 'assistant'
  content: string
  toolCalls: ToolCallState[]
  handoffs: { from: string; to: string }[]
  model?: string
  error?: string
  activeAgent?: string
  currentActivity?: string
}

export interface ToolCallState {
  toolCallId: string
  name: string
  arguments: Record<string, unknown>
  result?: unknown
  success?: boolean
  status: 'pending' | 'running' | 'success' | 'error'
}
