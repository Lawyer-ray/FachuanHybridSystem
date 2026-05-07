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

export type AgentType = 'triage' | 'case' | 'contract' | 'research'

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

// ─── 建议提示 ───────────────────────────────────────────────────────────────

export interface SuggestedPrompt {
  label: string
  prompt: string
  agent?: AgentType
  icon: string
}

export const SUGGESTED_PROMPTS: SuggestedPrompt[] = [
  { label: '查询案件', prompt: '帮我查询最近的案件列表', agent: 'case', icon: 'Briefcase' },
  { label: '合同审查', prompt: '帮我审查这份合同的风险条款', agent: 'contract', icon: 'FileText' },
  { label: '法律检索', prompt: '搜索相关的判例和法规', agent: 'research', icon: 'Search' },
  { label: '联网搜索', prompt: '帮我搜索最新的法律动态', icon: 'Globe' },
  { label: '创建提醒', prompt: '帮我创建一个开庭提醒', icon: 'Bell' },
  { label: '企业查询', prompt: '查询这家企业的工商信息', agent: 'research', icon: 'Building2' },
]

// ─── 批量分析 ───────────────────────────────────────────────────────────────

export type BatchJobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface BatchJob {
  id: string
  session_id: number
  job_type: string
  status: BatchJobStatus
  prompt: string
  llm_model: string
  total_items: number
  completed_items: number
  failed_items: number
  progress: number
  summary: string
  summary_file: string
  detail_zip_file: string
  error_message: string
  created_at: string
  updated_at: string
  started_at: string | null
  finished_at: string | null
  started_processing_at: string | null
  eta_seconds: number | null
  speed_per_minute: number
}

export interface BatchJobItem {
  id: string
  file_name: string
  status: BatchJobStatus
  result: string
  error: string
  duration_ms: number | null
}

export interface FailedItemDetail {
  id: string
  file_name: string
  error: string
}

export interface BatchProgress {
  job: BatchJob
  items: BatchJobItem[]
  failed_items_detail: FailedItemDetail[]
}
