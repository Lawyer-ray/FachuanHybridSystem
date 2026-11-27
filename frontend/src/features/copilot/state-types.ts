/**
 * store（useCopilot）的状态形状。
 *
 * 从 `types.ts` 拆出：它占据该文件近三分之一行数，且与「接口契约」是两回事——
 * 契约随后端变，状态形状随交互变。`types.ts` re-export 本接口，既有 import
 * 路径（`@/features/copilot/types`）不变。
 */

import type { AgentBackendSelection } from './backend-types'
import type { MentionInsert } from './domain/mention'
import type { CopilotContext } from './scope-types'
import type { UiActionRequest, UiToolErrorCode } from './ui-tools'
import type {
  ChatMessage,
  FolderRefDraft,
  PendingApproval,
  PendingQuestion,
  QuestionDraft,
  SelectionQuote,
  TurnStats,
} from './types'

/** 一次 UI 动作的运行态；失败码复用 ui-tools 的闭集（前端只认那几档） */
export interface UiToolRun {
  name: string
  state: 'pending' | 'running' | 'ok' | 'error' | 'aborted'
  code?: UiToolErrorCode
  startedAt: number
  endedAt?: number
}

/**
 * store（useCopilot）的完整状态形状。
 * 动作语义见各字段注释；实现见 store.ts（编排）与同域模块
 * （streaming / turn-handlers / outgoing / transitions / persistence）。
 */
export interface CopilotState extends AgentBackendSelection {
  sessionId: string | null
  messages: ChatMessage[]
  approvals: PendingApproval[]
  /**
   * 待回答的结构化提问（模型反问，与审批同层并列，不进转录）。
   *
   * 后端 `question_request` 事件已存在且答案回传端点已就绪；这里承载的只是
   * 「还没答的那几张卡」——超时不等于失效，补拉（loadPendingQuestions）也会写它。
   */
  pendingQuestions: PendingQuestion[]
  /** 提问草稿：键 = `${questionId}:${itemId}`（每道小题独立草稿，面板收起不丢） */
  questionDrafts: Record<string, QuestionDraft>
  /** 收到一条提问（事件入口；同 question_id 去重） */
  enqueueQuestion: (question: PendingQuestion) => void
  /** 写入/替换某道小题的草稿 */
  setQuestionDraft: (questionId: string, itemId: string, draft: QuestionDraft) => void
  /** 提交整组回答（一道未答等同跳过；提交在途置忙，失败保持可重提） */
  submitQuestion: (questionId: string) => Promise<void>
  /** 关闭一张提问卡（已答/已超时的僵尸卡；仅本地移除） */
  dismissQuestion: (questionId: string) => void
  /** 拉取服务端待答提问并合并（面板打开/重开会话时补拉，避免错过反问） */
  loadPendingQuestions: () => Promise<void>
  /**
   * UI 动作的运行记录（键 = `callId`）。
   *
   * **不进转录**：动作的结果已经落在页面上（页面跳了、面板开了），写进消息既回放不出
   * 那个效果，也无法撤销，只会在对话里多一行噪音（理由见 store/ui-tools.ts 文件头）。
   */
  uiToolRuns: Record<string, UiToolRun>
  /** 「停下」的置位时刻（null = 未打断）：此后到达的 ui_action 一律不执行 */
  abortedAt: number | null
  /** 执行一条界面动作（幂等 / 打断 / 失败落态都在 store/ui-tools.ts 收口） */
  runUiAction: (req: UiActionRequest) => Promise<void>
  /** 「停下」：只挡后续动作，已发出的不追回（它们在毫秒内已落完） */
  abortUiActions: () => void
  streaming: boolean
  loadingHistory: boolean
  /**
   * 当前会话的历史拉取失败（只由 switchSession 设置；切会话 / 历史成功加载时清除）。
   *
   * 与 `lastError` 分开：后者是「给律师看的最近一条错误」，发消息失败、限流、压缩
   * 失败都会写它；而「这个会话 id 可能是坏的」只能由「拉不到它的历史」推出来
   * （见 hooks/use-session-route 的坏 id 兜底）。
   */
  historyLoadError: boolean
  lastError: string | null
  /** 关闭当前错误提示（错误文案不自动消失：律师可能正看着它决定下一步） */
  clearError: () => void
  /** 本轮输出统计：流式期间驱动实时 tok/s，结束后展示精确 token 与平均速度 */
  turnStats: TurnStats
  /**
   * 分栏用量账（键 = 事件里的 `agent`，空串 = 单栏/未标注）。
   *
   * 多答的核心价值是**比较**：只并排几份答案、却看不出哪份更贵更慢，比较就
   * 只剩「读起来顺不顺」。单栏容量下 `turnStats` 仍然是同一份数据的聚合，
   * 旧 UI（TurnStatsView）不受影响。
   */
  turnStatsByLane: Record<string, TurnStats>
  /** 上下文水位（null = 未知/无会话）；done 事件与 stats/compact 接口回填 */
  contextUsage: { used: number | null; total: number | null }
  /** 后端正在压缩上下文（compaction 事件 start→end；手动压缩请求期间同为 true） */
  compacting: boolean
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
  /**
   * 待发送的 `@` 引用（案件 / 合同 / 文书 / 文件夹）。
   *
   * 与 `pendingRefs`（文件夹引用）与 `pendingQuote`（框选引用）并列，但**不是
   * 第三套 chip 渲染**：三者最终都由 `outgoing.ts` 拼成同一个出站协议块
   * （`[已引用文件：…]` / `[已引用选段：…]`），只是来源不同。
   */
  pendingMentions: MentionInsert[]
  /** 写入一条 @ 引用（同一对象重复引用只保留一条，顺序按首次引用） */
  addMention: (insert: MentionInsert) => void
  /** 移除一条 @ 引用（输入框里的引用 chip 点 ×） */
  removeMention: (kind: MentionInsert['kind'], refId: number | undefined, label: string) => void
  /** 清空 @ 引用（发送成功 / 切会话） */
  clearMentions: () => void
  /** 待发送的框选引用（编辑器选区进来后挂在输入框上方，随下一条消息发出） */
  pendingQuote: SelectionQuote | null
  /** 设置/清除待发送的框选引用（新选区直接覆盖旧的） */
  setPendingQuote: (quote: SelectionQuote | null) => void
  /** 通用模式的页面感知：用户当前所在页面的描述（详情页会写更精确值覆盖），send 注入 */
  pageHint: string | null
  /** 上一条已注入的页面描述：页面没变不重复注入，历史不刷屏 */
  lastPageHintSent: string | null
  /** 页面感知写入（AppShell 路由兜底 / 详情页精确覆盖） */
  setPageHint: (hint: string) => void
  /** 附件上传在途（发送按钮置忙，防止重复提交） */
  uploadingAttachments: boolean
  /**
   * 一次 send 的全过程在途（进入即置位，消息真正入列才清除）。
   *
   * 光靠 uploadingAttachments 不够：上传完成到消息入列之间它已被置回 false，
   * 而 streaming 还是 false，三个按钮同时解锁 → 二次 send 会重复上传同一批
   * 附件并把两条消息推进转录。所以用这个标志贯穿「建会话 → 上传附件 →
   * 消息入列」全程。
   */
  sending: boolean
  /** 拖拽文件悬停中（面板渲染投放离焦高亮） */
  draggingFiles: boolean
  /**
   * 本轮跑哪几个 agent（多答：1~{@link MAX_ANSWERS} 个，顺序 = 栏的左右顺序）。
   *
   * 默认 `[]`：按会话默认后端单跑。单元素 = 单跑指定后端，多元素 = 并排多栏。
   *
   * 为什么默认不多答：多一栏等于多跑一个模型、各自调工具，token 与耗时线性涨。
   * 它必须是律师每轮显式选择的动作，而不是一个悄悄变贵的默认。
   *
   * 空数组而不是 `[默认后端]`：默认后端是「部署给的」，前端清单没拉到时也算不出来
   * （见 store/turn.ts 的 resolveAnswerAgents）。
   */
  answerAgents: string[]
  /** 切换本轮参与的 agent（只影响下一轮，不重跑已发出的提问） */
  toggleAnswerAgent: (kind: string) => void
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
  /**
   * 重生成 / 续写一条已落库的回答（点哪一栏重跑哪一栏）。
   *
   * `fromMessageId` 是**库主键**（`ratableMessageId` 的结果）；`mode`：
   * `regenerate` 重跑同一提问、`continue` 接着被中断的前缀写。
   * 旧回答服务端只标 `superseded` 不删，流结束后拉一次历史对齐。
   */
  regenerate: (fromMessageId: number, mode: 'regenerate' | 'continue') => Promise<void>
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
  /** 写入上下文水位（done 事件 / stats / compact 回填的唯一写入口） */
  setContextUsage: (used: number | null, total: number | null) => void
  /** 拉取当前会话上下文水位（会话切换/新建后刷新；失败静默） */
  refreshContextUsage: () => Promise<void>
  /** 手动压缩当前会话上下文（slash 菜单 compact 命令）：成功 toast 新水位 */
  compactContext: () => Promise<void>
  /** 登出清理（换账号不得残留上一账号的会话内容） */
  reset: () => void
}
