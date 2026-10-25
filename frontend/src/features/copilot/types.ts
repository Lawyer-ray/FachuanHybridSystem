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
  /** 来源入口：chat（对话页）/ case（案件内）/ contract（合同内）/ task（任务式后台） */
  origin?: string
  case_id?: number | null
  contract_id?: number | null
  /** 业务范围名（案件名 / 委托人客户名，列表接口批量注水），通用与任务会话为空串 */
  scope_name?: string
  /** 任务式会话的进度（queued/running/succeeded/failed/cancelled）；非 task 会话为空串 */
  task_state?: string
  task_error?: string
  created_at: string
  updated_at: string
}

/** 会话分组（侧栏按业务范围分组展示，类 IDE 项目分组） */
export interface SessionGroup {
  key: string
  kind: 'contract' | 'case' | 'chat' | 'task'
  label: string
  sessions: AgentSession[]
  /** 业务范围的实体 id（合同/案件组才有）——侧栏据此判断「当前项目」 */
  refId?: number
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
  | { type: 'activity'; status: string; agent?: string; position?: number }
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
      /** 风险等级（low/medium/high/critical），服务端分级判定 */
      risk_level?: string
      /** 紧急级要求二次确认 */
      needs_second_confirmation?: boolean
    }
  | { type: 'error'; message: string }
  | {
      type: 'usage'
      output_tokens: number
      input_tokens?: number
      /** 缓存命中 token（pi usage.cacheRead） */
      cache_read_tokens?: number
      /** 缓存写入 token（pi usage.cacheWrite） */
      cache_write_tokens?: number
    }
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
  /** usage 事件的精确累计（未收到为 null）。**只算输出 token**：
   * 它用于展示生成速度，混进输入会让速度虚高数倍。 */
  exactTokens: number | null
  /** 本轮累计输入 token（未命中缓存部分） */
  inputTokens?: number
  /** 本轮缓存命中 token——前缀稳定的直接证据 */
  cacheReadTokens?: number
  /** 本轮缓存写入 token（前缀变过就会产生，是「cache 破了」的信号） */
  cacheWriteTokens?: number
  /** 采样点 [时间, 累计估算 token]，只保留近几秒 */
  samples: Array<[number, number]>
}

/** 转录气泡（历史回放与流式共用一个模型） */
/** 引用归属：合同绑定文件夹 / 案件绑定文件夹（两套独立绑定） */
export type RefOwnerKind = 'contract' | 'case'

/** 已发送消息里解析出的文件夹引用（chip 重放用；发送前草稿另见 FolderRefDraft） */
export interface SentRefMeta {
  kind: RefOwnerKind
  ownerId: number
  subpath: string
  name: string
  /** 目录引用：不落附件，靠 [已引用目录：…] 提示块让模型自行浏览 */
  isFolder?: boolean
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  /** user 消息里的文件夹引用（从「[已引用文件：…]」块解析，气泡上方重放为 chip） */
  refs?: SentRefMeta[]
  /** 通用模式下注入的页面锚点（从「[当前页面：…]」块解析，气泡上方重放为 chip） */
  pageHint?: string
  /** 业务范围（详情页工作区/浮层 context）下注入的归属锚点（从「[当前业务：…]」块解析） */
  bizHint?: string
  /** tool 消息的工具名（tool_call 与 tool_result 的归并键） */
  toolName?: string
  toolCallId?: string
  /** 回答被停止/断连截断（服务端 metadata.truncated 透传） */
  truncated?: boolean
  /** 用户反馈：点赞/点踩（历史回放透传，P1-9b） */
  rating?: 'up' | 'down'
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
  /** 风险等级（low/medium/high/critical） */
  riskLevel?: string
  /** 紧急级：同意前需二次确认 */
  needsSecondConfirmation?: boolean
  /** 离线待审（从 GET /approvals/pending 拉回，多来自后台任务），倒计时口径不同 */
  offline?: boolean
  /** 本地已提交决定后的终态展示 */
  decided?: 'approved' | 'rejected'
}

/** POST /agent/tasks 的受理回执 */
export interface AgentTaskReceipt {
  session_id: string
  task_id: string
  task_state: string
  title: string
}

/** 会话归属的业务范围（案件内 / 合同内）；不带则为普通对话 */
export interface CopilotScope {
  origin: 'case' | 'contract'
  refId: number
}

/** 业务内会话上下文（案件/合同页打开时携带）：范围 + 展示名 */
export interface CopilotContext extends CopilotScope {
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

/** 拖拽引用草稿：合同绑定文件夹内的文件（发送时落库为 ref 记录并附引用块） */
export interface FolderRefDraft {
  kind: RefOwnerKind
  ownerId: number
  subpath: string
  name: string
  isFolder?: boolean
}

/** 拖拽通道常量与 workbench 共用，定义上提 lib（此处 re-export 便于域内引用） */
export { FOLDER_REF_MIME } from '@/lib/folder-ref'

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

/**
 * store（useCopilot）的完整状态形状。
 * 动作语义见各字段注释；实现见 store.ts（编排）与同域模块
 * （streaming / turn-handlers / outgoing / transitions / persistence）。
 */
export interface CopilotState {
  sessionId: string | null
  messages: ChatMessage[]
  approvals: PendingApproval[]
  streaming: boolean
  loadingHistory: boolean
  lastError: string | null
  /** 本轮输出统计：流式期间驱动实时 tok/s，结束后展示精确 token 与平均速度 */
  turnStats: TurnStats
  /** 池满排队中：队列名次（1 起）；null = 不在排队 */
  queuePosition: number | null
  /** 本轮已插话（steer）且尚未撤回的文本 */
  queuedSteers: string[]
  /** 插话请求在途（防重复提交） */
  steering: boolean
  /** 业务内会话上下文（null = 普通对话模式）；会话列表按它过滤、新会话带归属 */
  context: CopilotContext | null
  /** 待发送附件（拖拽/选择后暂存，随下一条消息上传并引用） */
  pendingFiles: File[]
  /** 待发送的文件夹引用（从合同目录树拖入；随下一条消息落库并引用） */
  pendingRefs: FolderRefDraft[]
  /** 通用模式的页面感知：用户当前所在页面的描述（详情页会写更精确值覆盖），send 注入 */
  pageHint: string | null
  /** 上一条已注入的页面描述：页面没变不重复注入，历史不刷屏 */
  lastPageHintSent: string | null
  /** 页面感知写入（AppShell 路由兜底 / 详情页精确覆盖） */
  setPageHint: (hint: string) => void
  /** 附件上传在途（发送按钮置忙，防止重复提交） */
  uploadingAttachments: boolean
  /** 拖拽文件悬停中（面板渲染投放离焦高亮） */
  draggingFiles: boolean
  /** 拖拽/选择加入待发附件（前端预检不过的拒绝并提示） */
  addAttachmentFiles: (files: FileList | File[]) => void
  /** 移除一个待发附件 */
  removeAttachmentFile: (index: number) => void
  /** 加入一个待发文件夹引用（同 contractId+subpath 去重） */
  addFolderRef: (draft: FolderRefDraft) => void
  /** 移除一个待发文件夹引用 */
  removeFolderRef: (index: number) => void
  /** 进入业务内会话模式（案件/合同页打开）：列表过滤到该业务，新会话带归属 */
  enterContext: (context: CopilotContext) => Promise<void>
  /** 退出业务内会话模式，回到普通对话 */
  exitContext: () => Promise<void>
  /** 切换会话（null = 新对话）；会先停掉在途流再回放历史 */
  switchSession: (id: string | null) => Promise<void>
  /**
   * 发消息并消费 SSE 流；无会话时先创建。
   * onQueued 在「消息已入列开流（true）」或「早失败未发出（false，如建会话/
   * 上传附件失败）」时同步回调一次——调用方（Composer）据此决定是否回填正文。
   * 注意 send 的 Promise 要等整轮流结束才 resolve，不要用它做快速反馈。
   */
  send: (text: string, onQueued?: (sent: boolean) => void) => Promise<void>
  /** 停止生成（中断在途流） */
  stop: () => void
  /** 审批决定：本地即时标记，提交失败保持现状（服务端超时 fail-closed）；拒绝可附理由 */
  decide: (approvalId: string, approved: boolean, reason?: string) => Promise<void>
  /** 运行中插话：当前轮工具调用后、下次模型调用前生效 */
  steer: (text: string) => Promise<void>
  /** 撤回已排队未生效的全部插话 */
  revokeQueuedSteers: () => Promise<void>
  /** 提交后台任务（origin=task）：受理后切到该任务会话 */
  submitTask: (text: string) => Promise<void>
  /** 拉取离线待审批并合并进审批卡（面板打开 / 每轮流结束时调用） */
  loadPendingApprovals: () => Promise<void>
  /** 关闭一张审批卡（已决/已超时的僵尸卡；仅本地移除，不影响服务端状态） */
  dismissApproval: (approvalId: string) => void
  /** 给助手消息点赞/点踩（乐观更新，失败回滚；P1-9b） */
  rateMessage: (messageId: number, rating: 'up' | 'down' | 'none') => Promise<void>
  /** 加载更早的历史消息（游标分页，P1-3a）；没有更早时置 noMoreHistory */
  loadOlderHistory: () => Promise<void>
  /** 历史已到头（没有更早的消息了） */
  noMoreHistory: boolean
  /** 正在加载更早的消息 */
  loadingOlder: boolean
  /** 重拉当前会话历史（后台任务跑完后刷新转录用；流式中跳过） */
  refreshHistory: () => Promise<void>
  /** 登出清理（换账号不得残留上一账号的会话内容） */
  reset: () => void
}
