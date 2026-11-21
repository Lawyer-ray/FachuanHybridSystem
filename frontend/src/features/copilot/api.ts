/**
 * Copilot API 客户端：会话 CRUD 与流式发消息。
 *
 * 对流式请求的说明：后端是 POST 返回 SSE（见 agent_api.send_message），
 * EventSource 发不了 POST 也带不了 JWT 头，所以走 ky 拿原生 Response，
 * 由调用方（store）读 resp.body 流。ky 实例同时给了 JWT 注入与 401 刷新重试。
 */

import { api, UPLOAD_TIMEOUT_MS } from '@/lib/api'

import type { AgentAttachmentReceipt, AgentBackendOption, AgentCompactReceipt, AgentHistoryMessage, AgentSession, AgentSessionStats, AgentSkillList, AgentSkillToggleReceipt, AgentSpec, AgentTaskReceipt, CopilotScope, PendingApprovalItem, PendingQuestionItem, QuestionAnswerItem, QuestionAnswerReceipt, UsageSummary } from './types'

/** scope → 创建会话的请求体字段（origin + case_id/contract_id） */
function scopePayload(scope?: CopilotScope): Record<string, string | number> {
  if (!scope) return {}
  return {
    origin: scope.origin,
    ...(scope.origin === 'case' ? { case_id: scope.refId } : { contract_id: scope.refId }),
  }
}

export function listSessions(limit = 50, scope?: CopilotScope): Promise<AgentSession[]> {
  const searchParams: Record<string, string | number> = { limit }
  if (scope) {
    searchParams.origin = scope.origin
    searchParams[scope.origin === 'case' ? 'case_id' : 'contract_id'] = scope.refId
  }
  return api.get('agent/sessions', { searchParams }).json<AgentSession[]>()
}

/**
 * 新建会话。
 *
 * `agentKind` 是用户对后端的选择（`pi` / `dsh`），**会话级、建完不能改**（上下文
 * 归后端自己管）。空串表示不指定，由后端用默认值——不传时契约默认也是 `pi`。
 */
export function createSession(title = '', scope?: CopilotScope, agentKind = ''): Promise<AgentSession> {
  return api
    .post('agent/sessions', { json: { title, ...scopePayload(scope), ...(agentKind ? { agent_kind: agentKind } : {}) } })
    .json<AgentSession>()
}

/** 可选 agent 后端清单（切换器数据源；`available=false` 的项带不可用原因） */
export function fetchBackends(): Promise<AgentBackendOption[]> {
  return api.get('agent/backends').json<AgentBackendOption[]>()
}

export function deleteSession(sessionId: string): Promise<{ deleted: number }> {
  return api.delete(`agent/sessions/${sessionId}`).json<{ deleted: number }>()
}

/** 重命名会话（侧边栏改名入口；空标题后端 400） */
export function renameSession(sessionId: string, title: string): Promise<AgentSession> {
  return api.patch(`agent/sessions/${sessionId}`, { json: { title } }).json<AgentSession>()
}

export function fetchHistory(sessionId: string, limit = 200, beforeId?: number): Promise<AgentHistoryMessage[]> {
  const searchParams: Record<string, string | number> = { limit }
  if (beforeId) searchParams.before_id = beforeId
  return api.get(`agent/sessions/${sessionId}/messages`, { searchParams }).json<AgentHistoryMessage[]>()
}

/**
 * 评审 / 综合结论 / 采纳端点在 `review-api.ts`（`api.ts` 已到 450 行硬红线，按职责拆出）。
 *
 * 这里 re-export 保持既有 import 路径不变（`from './api'`），与 `types.ts` re-export
 * `backend-types.ts` 同口径；新增评审类端点请直接加到 `review-api.ts`。
 */
export {
  adoptReview,
  fetchReview,
  fetchReviewAdoption,
  fetchReviewOptions,
  fetchSynthesis,
  REVIEW_TIMEOUT_MS,
  runReview,
  runSynthesis,
} from './review-api'
export type { ReviewOptions } from './review-api'

/** 前端提交审批决定（同意/拒绝高危工具调用） */
export function decideApproval(approvalId: string, approved: boolean, reason = ''): Promise<Record<string, unknown>> {
  return api.post(`agent/approval/${approvalId}/decide`, { json: { approved, reason } }).json<Record<string, unknown>>()
}

/**
 * 发消息并返回未消费的 SSE Response（body 是 ReadableStream）。
 * ky 的 ResponsePromise 本身就是 Promise<Response>，await 即得原生 Response
 * （body 未消费，交给 store 读流）；非 2xx 会抛 HTTPError（SSE 端点恒 200，
 * 鉴权 401 由 ky 的 401 刷新钩子先行处理）。
 * `signal` 用于「停止生成」：中断即客户端断开，服务端会把已流出的
 * 部分回答落库（metadata.truncated），前端随后重拉历史即可对齐。
 */
/**
 * 打开一条 SSE 流。
 *
 * `agents`：本轮跑哪几个 agent、各用哪个模型（顺序 = 栏的左右顺序）。契约见
 * 后端 `MessageIn.agents: list[AgentSpecIn | str] | None`——两种形状都收（老前端
 * 发纯字符串），前端**统一发对象** `{kind, model?}`：只留一种写法，`model` 缺省
 * 即平台默认，与发纯字符串等价。
 *
 * 下发规则（**空数组一律不发**）：
 * - 0 个：不传字段，后端用会话自己的 `agent_kind` 单跑——后端契约默认值
 *   （`None` → 单栏）就是它，多传一个空数组只会让「默认」出现两个真相；
 * - 1 个：只发 `agents`（单跑指定后端）；
 * - 2~4 个：多答，事件靠 `agent` 字段分流到各自的栏。
 *
 * **不发 `dual`**：那是个布尔，只能表达「两个」。后端保留它只为兼容老客户端；
 * 新前端只用 `agents`，避免「dual=true 同时 agents=[a,b,c]」这种需要猜优先级的
 * 请求（虽然后端口径是「显式 > 隐式」，但前端不该依赖两条路径的一致性）。
 *
 * 上限 `MAX_ANSWERS = 4` 由 store 在调用前截断（见 store/turn.ts），后端超限
 * 直接回一条 `error` 事件（不静默截断），所以前端必须先截——用户敲回车之后
 * 才被告知「选多了」是很差的体验。
 */
export function openMessageStream(
  sessionId: string,
  message: string,
  signal: AbortSignal,
  agents: AgentSpec[] = [],
): Promise<Response> {
  const json = agents.length > 0 ? { message, agents } : { message }
  return api.post(`agent/sessions/${sessionId}/messages`, { json, signal })
}

/** 运行中插话：当前 assistant turn 的工具调用跑完后、下次模型调用前生效（后端 steer） */
export function steerSession(sessionId: string, message: string): Promise<{ success: boolean; disposition: string }> {
  return api.post(`agent/sessions/${sessionId}/steer`, { json: { message } }).json<{ success: boolean; disposition: string }>()
}

/** 撤回已排队未生效的插话/追加（返回被撤回的原文） */
export function clearSessionQueue(sessionId: string): Promise<{ success: boolean; messages: string[] }> {
  return api.delete(`agent/sessions/${sessionId}/queue`).json<{ success: boolean; messages: string[] }>()
}

/** 提交后台任务：立即返回，agent 在后台跑，跑完写入会话的通知消息 */
export function submitAgentTask(message: string, title = '', scope?: CopilotScope): Promise<AgentTaskReceipt> {
  return api.post('agent/tasks', { json: { message, title, ...scopePayload(scope) } }).json<AgentTaskReceipt>()
}

/** 当前用户近 N 天的用量汇总（次数/token/失败率）；超管可 all=true 看全所 */
export function getUsageSummary(days = 30, all = false): Promise<UsageSummary> {
  return api.get('agent/usage', { searchParams: { days, ...(all ? { all: 'true' } : {}) } }).json<UsageSummary>()
}

/** 当前用户仍待处理的审批（离线审批入口：后台任务挂起的高危工具调用） */
export function fetchPendingApprovals(): Promise<PendingApprovalItem[]> {
  return api.get('agent/approvals/pending').json<PendingApprovalItem[]>()
}

/** 上传对话附件（multipart 字段 file；服务端白名单/20MB 限额，返回引用 id） */
export function uploadAttachment(sessionId: string, file: File): Promise<AgentAttachmentReceipt> {
  const form = new FormData()
  form.append('file', file)
  return api
    .post(`agent/sessions/${sessionId}/attachments`, { body: form, timeout: UPLOAD_TIMEOUT_MS })
    .json<AgentAttachmentReceipt>()
}

/** 创建文件夹引用（拖拽合同目录树文件；不复制字节，返回引用回执） */
export function createFolderRef(
  sessionId: string,
  kind: 'contract' | 'case',
  ownerId: number,
  subpath: string,
): Promise<AgentAttachmentReceipt> {
  return api
    .post(`agent/sessions/${sessionId}/folder-refs`, { json: { kind, owner_id: ownerId, subpath } })
    .json<AgentAttachmentReceipt>()
}

/** 合同绑定文件夹的某一层条目（目录树懒加载数据源，非递归） */
export interface FolderEntries {
  browsable: boolean
  message: string | null
  path_display: string
  subpath: string
  parent_subpath: string
  folders: { name: string; subpath: string }[]
  files: { name: string; subpath: string; size: number; modified_at: string }[]
}

/**
 * 合同绑定文件夹某一层。`signal` 供 `@` 引用源的中断（查询词变了就 abort 上一轮）。
 *
 * 契约：`backend/apps/contracts/api/folder_binding_api.py`（路由前缀 `/contracts`
 * 由 `backend/apiSystem/apiSystem/api.py:217` 装配）。
 */
export function fetchContractFolderEntries(contractId: number, subpath = '', signal?: AbortSignal): Promise<FolderEntries> {
  return api
    .get(`contracts/${contractId}/folder-entries`, { searchParams: subpath ? { subpath } : {}, ...(signal ? { signal } : {}) })
    .json<FolderEntries>()
}

/**
 * 案件绑定文件夹某一层（与合同版同形：`CaseFolderEntriesResponseSchema` 与
 * `ContractFolderEntriesOut` 的 folders/files 字段一致）。
 *
 * 契约：`backend/apps/cases/api/case_folder_browse_api.py:54`
 * `GET /{case_id}/folder-entries?subpath=`，前缀 `/cases` 见 api.py:215。
 */
export function fetchCaseFolderEntries(caseId: number, subpath = '', signal?: AbortSignal): Promise<FolderEntries> {
  return api
    .get(`cases/${caseId}/folder-entries`, { searchParams: subpath ? { subpath } : {}, ...(signal ? { signal } : {}) })
    .json<FolderEntries>()
}

/** 业务范围 → 绑定文件夹某一层的条目（案件/合同两个端点同形，合并成一个入口） */
export function fetchScopeFolderEntries(
  scope: CopilotScope,
  subpath = '',
  signal?: AbortSignal,
): Promise<FolderEntries> {
  return scope.origin === 'case'
    ? fetchCaseFolderEntries(scope.refId, subpath, signal)
    : fetchContractFolderEntries(scope.refId, subpath, signal)
}

/** `@` 引用的文书/目录候选源要的行（本前端只用名字/路径/大小） */
export interface ScopeFolderRows {
  browsable: boolean
  message: string | null
  folders: { name: string; subpath: string }[]
  files: { name: string; subpath: string; size: number }[]
}

/** 候选源再下钻几层子目录（多几次请求换「@起诉状」在真实目录结构上真能命中） */
export const SCOPE_SUBDIR_SCAN = 6

/** 绑定文件夹候选的缓存（一个业务范围一份）：候选集不随查询词变化，重复拉没意义 */
const scopeRowsCache = new Map<string, Promise<ScopeFolderRows>>()

/** 测试 / 绑定文件夹变更后用：清掉候选缓存 */
export function clearScopeFolderRowsCache(): void {
  scopeRowsCache.clear()
}

/**
 * 业务范围 → 绑定文件夹里可 @ 的文件与子目录（根层 + 前 {@link SCOPE_SUBDIR_SCAN} 个子目录）。
 *
 * 为什么带下钻：文书几乎不在绑定根（典型是 `1-一审/2-立案材料/起诉状.pdf`），只列根
 * 会让 `@起诉状` 永远搜不到真正想引的东西。结果按 `origin:refId` 缓存——一次打开菜单
 * 只发一轮请求，之后每个查询词都命中缓存。
 *
 * **已知局限**（需后端端点才能根治，见产出）：深层（≥3 级）文书搜不到，且无服务端
 * 递归检索能力；单个子目录读失败只跳过它（换机器/权限变了的目录很常见）。
 *
 * 注：错误不进缓存（用户到详情页重新绑定后重试应该能看到变化）。
 */
export function loadScopeFolderRows(scope: CopilotScope): Promise<ScopeFolderRows> {
  const key = `${scope.origin}:${scope.refId}`
  const cached = scopeRowsCache.get(key)
  if (cached) return cached
  const pending = (async (): Promise<ScopeFolderRows> => {
    const root = await fetchScopeFolderEntries(scope)
    if (!root.browsable) return { browsable: false, message: root.message, folders: [], files: [] }
    const subdirs = root.folders.slice(0, SCOPE_SUBDIR_SCAN)
    const deeper = await Promise.allSettled(subdirs.map((folder) => fetchScopeFolderEntries(scope, folder.subpath)))
    const files = root.files.map(({ name, subpath, size }) => ({ name, subpath, size }))
    for (const result of deeper) {
      if (result.status !== 'fulfilled' || !result.value.browsable) continue
      for (const { name, subpath, size } of result.value.files) files.push({ name, subpath, size })
    }
    return { browsable: true, message: null, folders: root.folders, files }
  })().catch((error: unknown) => {
    scopeRowsCache.delete(key)
    throw error
  })
  scopeRowsCache.set(key, pending)
  return pending
}

/** 项目笔记的回执（`POST /agent/memory/notes` 的 `MemoryOut` 子集） */
export interface ProjectNoteReceipt {
  id: string
  content: string
  contract_id: number | null
  case_id: number | null
  /** 非空 = 已有人点过确认（项目事实）；空 = 同事的判断 */
  confirmed_at: string
}

/**
 * 把一条结论存进项目笔记（同团队可见）。
 *
 * **只传 sessionId**：前端拿不到可靠的 `contract_id`（案件页的 `CopilotScope`
 * 只有 case_id），让前端猜锚点必然把结论写到错的项目上。锚点由服务端按会话
 * 归属反查，会话不属于自己时按「没有锚点」处理。
 */
export function createProjectNote(input: {
  content: string
  sessionId: string
  kind?: string
}): Promise<ProjectNoteReceipt> {
  return api
    .post('agent/memory/notes', {
      json: {
        content: input.content,
        session_id: input.sessionId,
        ...(input.kind ? { kind: input.kind } : {}),
      },
    })
    .json<ProjectNoteReceipt>()
}

/** 全局搜索的一条结果（`core/api/search_api.py` 的 `SearchResultItem`） */
export interface GlobalSearchItem {
  id: number
  title: string
  subtitle: string
  side: string
  case_type: string
  contract_id: number | null
  contract_name: string
}

/**
 * `GET /search` 的返回（`GlobalSearchResult`）：六类固定键，本前端只用两类的标题/副标题。
 *
 * 为什么用全局搜索做 `@案件` / `@合同` 的候选源：它不是为引用写的，但它是**唯一**
 * 按关键词跨案件/合同检索、且已做行级 ACL 过滤的端点（`search_service.py` 每条
 * search_* 都接 user/org_access）。单类列表端点（`GET /cases`）要自己拼过滤词，
 * 且搜索口径会与全局搜索漂移。
 */
export interface GlobalSearchResult {
  clients: GlobalSearchItem[]
  cases: GlobalSearchItem[]
  contracts: GlobalSearchItem[]
  inbox: GlobalSearchItem[]
  court_sms: GlobalSearchItem[]
  contacts: GlobalSearchItem[]
}

/**
 * 跨实体关键词搜索。契约：`backend/apps/core/api/search_api.py:52`
 * `GET /search?q=&limit=`（前缀 `/search` 见 api.py:320）。
 *
 * `q` 为空时后端直接回空（不是错误）；`limit` 服务端硬顶 10。
 */
export function globalSearch(q: string, limit = 5, signal?: AbortSignal): Promise<GlobalSearchResult> {
  return api.get('search', { searchParams: { q, limit }, ...(signal ? { signal } : {}) }).json<GlobalSearchResult>()
}

/** 给一条助手消息点赞/点踩（反馈回流；rating: up/down/none，none=撤销） */
export function rateMessage(messageId: number, rating: 'up' | 'down' | 'none'): Promise<Record<string, unknown>> {
  return api.post(`agent/messages/${messageId}/rating`, { json: { rating } }).json<Record<string, unknown>>()
}

/**
 * 提交结构化提问的回答（模型反问的答案回流）。
 *
 * 字段名对齐后端 `QuestionAnswerIn`：`answers[].selections/text/comment` +
 * `skipped`。`success=false` 不等于失败——等待方可能已超时（律师过了 180s 才
 * 点提交），此时答案仍被记录、模型已按假设继续；调用方应按「已记录但本轮已继续」
 * 提示，不要当成错误重试。
 */
export function answerQuestion(
  questionId: string,
  payload: { answers: QuestionAnswerItem[]; skipped: boolean },
): Promise<QuestionAnswerReceipt> {
  return api.post(`agent/question/${questionId}/answer`, { json: payload }).json<QuestionAnswerReceipt>()
}

/** 当前律师待回答的提问（重开会话/面板时补拉，避免错过模型的反问） */
export function fetchPendingQuestions(): Promise<PendingQuestionItem[]> {
  return api.get('agent/questions/pending').json<PendingQuestionItem[]>()
}

/** 取消后台任务（排队中可取消；运行中诚实 409） */
export function cancelAgentTask(sessionId: string): Promise<Record<string, unknown>> {
  return api.delete(`agent/tasks/${sessionId}`).json<Record<string, unknown>>()
}

/** 技能清单（`/` 命令菜单数据源；消息以 `/skill:名字 参数` 触发，后端 pi 展开） */
export function fetchAgentSkills(): Promise<AgentSkillList> {
  return api.get('agent/skills').json<AgentSkillList>()
}

/** 启停一个技能（name 为技能名；返回终态回执） */
export function setAgentSkillEnabled(name: string, enabled: boolean): Promise<AgentSkillToggleReceipt> {
  return api.patch(`agent/skills/${name}`, { json: { enabled } }).json<AgentSkillToggleReceipt>()
}

/** 会话 token 用量与上下文水位（上下文水位驱动 Composer 底部的水位指示） */
export function fetchSessionStats(sessionId: string): Promise<AgentSessionStats> {
  return api.get(`agent/sessions/${sessionId}/stats`).json<AgentSessionStats>()
}

/** 手动压缩会话上下文：总结历史释放空间，返回压缩后水位 */
export function compactSession(sessionId: string): Promise<AgentCompactReceipt> {
  return api.post(`agent/sessions/${sessionId}/compact`).json<AgentCompactReceipt>()
}
