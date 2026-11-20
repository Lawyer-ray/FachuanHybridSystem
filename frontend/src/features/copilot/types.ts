/**
 * Copilot 域类型：/api/v1/agent 的接口契约与前端转录模型。
 * 后端事件契约见 backend/apps/agent/services/chat_service.py 顶部注释。
 *
 * 几个自成一节、且体量足以撞软红线的类型单独成文件，此处 re-export 保持既有
 * import 路径（`@/features/copilot/types`）不变：
 * - `backend-types.ts`：可选 agent 后端与「新建会话用哪个」的选择字段；
 * - `scope-types.ts`：会话归属的业务范围（案件内 / 合同内）；
 * - `skill-types.ts`：技能清单与启停回执（`/` 菜单的数据源）；
 * - `state-types.ts`：store 的状态形状（`CopilotState`）。
 */

import type { CitationRef } from './domain/knowledge'
import type { QuestionItem } from './domain/question'

export type { CitationRef, CitationKind } from './domain/knowledge'
export type { MentionCandidate, MentionInsert, MentionKind } from './domain/mention'
export type { AgentBackendOption, AgentSpec } from './backend-types'
export type { CopilotContext, CopilotScope } from './scope-types'
export type { AgentSkill, AgentSkillList, AgentSkillToggleReceipt } from './skill-types'

/** 会话（GET/POST /agent/sessions） */
export interface AgentSession {
  session_id: string
  title: string
  status: string
  /** 最近一轮实际使用的模型（服务端回写；未对话过为空） */
  llm_model: string
  /**
   * 本会话使用的 agent 后端（`pi` / `dsh`）。
   *
   * **会话级属性、不可中途更换**：上下文归后端自己管（pi 有自己的 session 文件），
   * 换后端等于换脑子，前面的对话对它不存在。所以已建会话只用于展示，切换器
   * 只在新会话时可选。
   */
  agent_kind: string
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
  /** 消息级来源（`pi` / `dsh` / 新注册的后端）；空串 = 旧数据 / 未标注（按 `pi` 处理） */
  agent_kind?: string
  created_at: string
  metadata: Record<string, unknown>
}

/**
 * SSE 流事件（POST /agent/sessions/{id}/messages 的 data 帧）。
 * 单一来源是自动生成的 sse-events.ts（`python -m apps.agent.sse_types --ts`
 * 重新生成，后端定义在 apps/agent/sse_types.py）——此处仅 re-export，
 * 禁止手抄一份（会漂移）。
 */
export type { AgentStreamEvent } from './sse-events'

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

/**
 * 框选引用（豆包式）：律师在 OnlyOffice 里选中一段文本后，引用以卡片挂在
 * 输入框上方（不是把模板文字灌进输入框），随下一条消息以
 * 「[已引用选段：…]」块发出。发送前草稿与已发送回放共用一个形状。
 */
export interface SelectionQuote {
  kind: RefOwnerKind
  ownerId: number
  subpath: string
  name: string
  /** 选中的文本（换行已归一为空格、限长截断） */
  text: string
}

/**
 * 业务归属锚点（详情页工作区/浮层 context 下每轮注入的 `[当前业务：…]` 块）。
 *
 * 出站构建（domain.buildBizHintBlock）与历史回放解析（domain.splitBizHintLine）
 * 产出的都是这个形状——两侧不得漂移。展示层按三段渲染（单位/名称/#id），
 * 不再把整串交给 `truncate`（那会把唯一的机器可读归属 id 截掉）。
 */
export interface BizHint {
  /** 业务范围：合同（委托）还是案件 */
  kind: RefOwnerKind
  /** 委托/案件名（标题里的 `「」` 已归一为 `“”`） */
  title: string
  /** 合同 id / 案件 id */
  refId: number
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'tool'
  /**
   * 落库主键（历史回放来自 `AgentHistoryMessage.message_id`）。
   *
   * 实时气泡没有它（还没落库），所以「能否评分/能否当翻页游标」必须看这个
   * 字段而不是从 `id` 里反推——旧代码 `Number('local-1'.slice(3))` 得到 NaN，
   * 按钮可点但请求必然失败（见 domain/message-id.ts）。
   */
  serverId?: number
  /** 发生时刻（ms）。历史回放来自 `created_at`；实时气泡为本地收到时刻 */
  createdAt?: number
  content: string
  /** user 消息里的文件夹引用（从「[已引用文件：…]」块解析，气泡上方重放为 chip） */
  refs?: SentRefMeta[]
  /** user 消息里的框选引用（从「[已引用选段：…]」块解析，气泡上方重放为引用卡） */
  quote?: SelectionQuote
  /** 通用模式下注入的页面锚点（从「[当前页面：…]」块解析，气泡上方重放为 chip） */
  pageHint?: string
  /** 业务范围（详情页工作区/浮层 context）下注入的归属锚点（从「[当前业务：…]」块解析） */
  bizHint?: BizHint
  /** tool 消息的工具名（tool_call 与 tool_result 的归并键） */
  toolName?: string
  toolCallId?: string
  /**
   * `rewrite_folder_file` 的改写对（原文片段 / 改写全文），用来在工具行里画出
   * 「改了哪一句」。
   *
   * **数据源只有 `tool_call.arguments`**：`tool_result.result` 在 SSE 里被截到
   * 2000 字读不回全文（见 `domain/reference.ts` 的长注释），所以这里存的是**参数**
   * 而不是结果；`filePath` 是参数里的 `subpath` 去掉目录后的显示名。
   *
   * 工具可能发多条 `tool_call`（arguments 渐进完整），后到的解析结果覆盖前一条。
   */
  rewrite?: { original: string; replacement: string; filename?: string }
  /** 回答被停止/断连截断（服务端 metadata.truncated 透传） */
  truncated?: boolean
  /** 用户反馈：点赞/点踩（历史回放透传，P1-9b） */
  rating?: 'up' | 'down'
  /** 正在流式接收中（assistant 专属） */
  streaming?: boolean
  /**
   * 这一栏本轮没跑成（多答时某后端报错/配额降级）：渲染为「本轮未做」。
   *
   * 只标失败那一栏，其他栏的正文照常显示——不标的话界面上就是个空白栏头，
   * 看起来像「回答了但内容丢了」。
   */
  failed?: boolean
  /** 模型的思考过程（开启思考模式时由 thinking 事件累积，仅展示不入正文） */
  thinking?: string
  /** 思考已完成（收到首个正文 delta 后置位，用于折叠/收起样式） */
  thinkingDone?: boolean
  /**
   * 这条回答/工具行由哪个 agent 产出（`pi` / `dsh`）。
   *
   * 多答时一轮里有 2~4 条 assistant 消息，各带自己的 agent；单后端轮次只有
   * 一条。**空串/undefined 表示旧数据 / 未标注**，渲染时当 `pi` 处理——引入
   * 多答之前本系统只有 pi 在跑（见后端 AgentMessage.agent_kind 注释）。
   */
  agentKind?: string
  /**
   * 这条回答用的模型名（栏头显示「agent · 模型」的数据源）。
   *
   * 律师引入多答就是为了**比较效果**：栏头不写模型，看到几份不同意见却分不清
   * 哪份是谁答的，比较就失去意义。
   *
   * 两条来源：本地发送时取自本轮指定（`store/turn.ts` 建气泡那一刻就带上——
   * 后端事件里没有 model 字段）；历史回放取自 `metadata.model`（后端在流结束时
   * 落库的实际模型）。未指定 / 旧数据时 undefined，栏头只显示 agent 名。
   */
  model?: string
  /**
   * 这条回答引用的材料（入站引用，AI → 材料）。
   *
   * 与 `refs` / `quote`（出站引用）**方向相反、字段不共用**：那两个是律师给模型
   * 的东西，这个是模型给律师的溯源。正文里的 `[Kn]` 角标靠 `citeNo` 与这里对齐；
   * 缺字段 = 本轮没有来源（旧数据 / 后端未接），不是「引用丢失」。
   */
  citations?: CitationRef[]
  /**
   * 单栏时「此刻在等哪个工具返回」（驱动气泡内的「正在查 XX…」）。
   *
   * 为什么不复用 `tools`：`tools` 是多栏的**渲染槽**（栏下方那串 chip），单栏若
   * 也往里写就会把工具行渲染成两份。这个字段只喂 `activityText`，从不单独渲染。
   */
  pendingTool?: ChatMessage
  /**
   * 这条回答期间该 agent **自己**调用过的工具（按到达顺序）。
   *
   * 为什么挂在回答上而不是当独立消息渲染：多答时 2~4 个 agent 在**同一时刻**
   * 各调各的工具，转录里这些 tool 消息交错相邻（pi 的 get_current_user、dsh 的
   * tool_search、pi 的 list_lawyers…）。按时间平铺在一个列表里就变成截图里那
   * 样——一坨分不清谁的、还占满整行的工具条。
   *
   * 挂到各自的栏之后，读法是「这个 AI 查了什么、然后说了什么」，与人读对话的
   * 顺序一致。单栏（只有一个 agent）时不填这个字段，工具行仍按原样平铺在气泡
   * 之间——那条路径的时间顺序本身就是对的，没必要动。
   */
  tools?: ChatMessage[]
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
  /** 多答时哪个 agent 要动库表（审批事件带 `agent`；缺失 = 单栏/未标注） */
  agentKind?: string
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

/** `/` 命令菜单项（技能补全 / 内置命令）；构建与过滤见 domain.ts，交互见 hooks/use-slash-menu */
export interface SlashMenuItem {
  /** 列表 key（`skill-名` / `command-名`） */
  key: string
  kind: 'skill' | 'command'
  /** 技能名 / 命令 id（技能补全文本、命令触发动作用） */
  id: string
  /** 展示名：技能名 / 命令中文标签 */
  label: string
  description: string
  /** 不可选（如无活动会话时的 compact） */
  disabled?: boolean
  /** 禁用原因（菜单项小字提示，如「先开始对话」） */
  disabledHint?: string
}

/** store 状态形状定义在同目录 `state-types.ts`（体量与关注点都与契约不同） */

/** 结构化提问的题面类型由纯领域模块定义（回流类型与契约分属两处） */
export type { QuestionAnswerItem, QuestionDraft, QuestionItem, QuestionOption } from './domain/question'
export type { CopilotState } from './state-types'
