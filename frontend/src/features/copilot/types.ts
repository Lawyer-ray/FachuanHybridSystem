/**
 * Copilot 域类型：/api/v1/agent 的接口契约与前端转录模型。
 * 后端事件契约见 backend/apps/agent/services/chat_service.py 顶部注释。
 *
 * 几个自成一节、且体量足以撞软红线的类型单独成文件，此处 re-export 保持既有
 * import 路径（`@/features/copilot/types`）不变：
 * - `backend-types.ts`：可选 agent 后端与「新建会话用哪个」的选择字段；
 * - `scope-types.ts`：会话归属的业务范围（案件内 / 合同内）；
 * - `skill-types.ts`：技能清单与启停回执（`/` 菜单的数据源）；
 * - `state-types.ts`：store 的状态形状（`CopilotState`）；
 * - `memory-types.ts`：记忆条目、策展候选与可策展作用域；
 * - `api-types.ts`：端点收发形状（审批 / 提问 / 任务 / 附件 / usage / stats / compact 回执）。
 *
 * 这份清单是拆分契约：从这里再搬走一块，必须同步补一行，否则下一个人不知道它存在。
 */

import type { CitationRef } from './domain/knowledge'
import type { LaneUsage } from './domain/usage'
import type { ToolRunState } from './domain/tool-view'

export type { CitationRef, CitationKind } from './domain/knowledge'
export type { MentionCandidate, MentionInsert, MentionKind } from './domain/mention'
export type { AgentBackendOption, AgentSpec, QoderAuthState, QoderByokState, QoderLoginState } from './backend-types'
export type { CopilotContext, CopilotScope } from './scope-types'
export type {
  AgentSkill,
  AgentSkillCreateInput,
  AgentSkillDetail,
  AgentSkillList,
  AgentSkillQuota,
  AgentSkillScope,
  AgentSkillSource,
  AgentSkillToggleReceipt,
  AgentSkillUpdateInput,
  AgentSkillValidation,
  AgentSkillValidationError,
} from './skill-types'
export type {
  AgentMemoryItem,
  MemoryKind,
  MemoryScopes,
  MemoryScope,
  MemoryStatus,
  PromoteCandidate,
} from './memory-types'

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
  /**
   * 律师反馈（后端 `MessageOut.rating`）。空串 = 未评分；缺失 = 旧后端。
   *
   * `metadata.rating` 里也有同值，但顶层字段是**契约**：前端不该去猜后端把
   * 反馈存在 metadata 的哪个键里（那是实现细节，改名就静默失效）。
   */
  rating?: 'up' | 'down' | ''
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

export interface ChatMessage extends ToolRunState {
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
   * 两条来源：本地发送时取自本轮指定（`store/turn-send.ts` 建气泡那一刻就带上——
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
   * 这一栏这一轮的历史用量（刷新后栏头 chip 的数据源）。
   *
   * 与 `turnStatsByLane`（内存里只活一轮）是**同一形状的两种来源**：那份是实时账、
   * 每轮清空；这份来自后端落库的 `metadata.usage_by_lane` + `ttft_ms`，由
   * `domain/usage.laneUsageFromMetadata` 收窄。两条来源共用一个 `LaneUsage`，
   * 否则刷新前后同一栏会出现两个数。
   */
  laneUsage?: LaneUsage
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

export type {
  AgentAttachmentReceipt,
  AgentCompactReceipt,
  AgentSessionStats,
  AgentTaskReceipt,
  PendingApproval,
  PendingApprovalItem,
  PendingQuestion,
  PendingQuestionItem,
  QuestionAnswerReceipt,
  UsageSummary,
} from './api-types'

/**
 * `/` 命令菜单项（技能补全 / 内置命令）；构建与过滤见 domain.ts，交互见 hooks/use-slash-menu。
 * 字段口径：`key` 是列表 key（`skill-<技能key>` / `command-名`）；`id` 是技能名 / 命令 id；
 * `label` 是展示名；`badge` 是标题右侧的小徽标（技能项为「我的 / 系统」，命令项无）；
 * `disabled` + `disabledHint` 表示不可选与原因（如「先开始对话」）。
 */
export interface SlashMenuItem {
  key: string
  kind: 'skill' | 'command'
  id: string
  label: string
  description: string
  badge?: string
  disabled?: boolean
  disabledHint?: string
}

/** store 状态形状在同目录 `state-types.ts`（体量与关注点都与契约不同）；
 *  结构化提问的题面类型由纯领域模块定义（回流类型与契约分属两处） */
export type { QuestionAnswerItem, QuestionDraft, QuestionItem, QuestionOption } from './domain/question'
export type { CopilotState } from './state-types'
/** 多答裁决卡视图（camelCase；线上契约→视图的映射见 domain/fusion.ts） */
export type { ClusterView, ConflictPairView, ConflictSideView, LaneView, ReviewView, VerdictView } from './domain/fusion'
/** 评审采纳记录视图（独立端点，不进冻结的 Review 快照；见 domain/adoption.ts） */
export type { AdoptionView } from './domain/adoption'
