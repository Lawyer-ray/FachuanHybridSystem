/**
 * Copilot API 客户端：会话 CRUD 与流式发消息。
 *
 * 对流式请求的说明：后端是 POST 返回 SSE（见 agent_api.send_message），
 * EventSource 发不了 POST 也带不了 JWT 头，所以走 ky 拿原生 Response，
 * 由调用方（store）读 resp.body 流。ky 实例同时给了 JWT 注入与 401 刷新重试。
 *
 * 按职责拆出去的部分（本文件只 re-export，import 路径一律不变）：
 * - `review-api.ts`      评审 / 综合结论 / 采纳（8 个端点）
 * - `memory-api.ts`      记忆域（含 @see createProjectNote 项目笔记，同为 `agent/memory` 前缀）
 * - `api/folders.ts`     绑定文件夹浏览（contracts / cases 两个后端域；契约在 `api/folder-types.ts`）
 * - `api/mention-sources.ts` `@` 引用的跨实体候选源（core `search/`；契约在 `api/search-types.ts`）
 */

import { api, UPLOAD_TIMEOUT_MS } from '@/lib/api'

import type { AgentAttachmentReceipt, AgentBackendOption, AgentCompactReceipt, AgentHistoryMessage, AgentSession, AgentSessionStats, AgentSkillList, AgentSkillToggleReceipt, AgentSpec, AgentTaskReceipt, CopilotScope, PendingApprovalItem, PendingQuestionItem, QuestionAnswerItem, QuestionAnswerReceipt, QoderAuthState, QoderByokState, QoderLoginState, UsageSummary } from './types'

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

/**
 * 目录树 / `@` 候选源 / 项目笔记：实现已按后端域拆到旁边三个文件，这里只
 * re-export（理由同上一段：import 路径不变）。
 */
export {
  clearScopeFolderRowsCache,
  fetchCaseFolderEntries,
  fetchContractFolderEntries,
  fetchScopeFolderEntries,
  loadScopeFolderRows,
  SCOPE_SUBDIR_SCAN,
} from './api/folders'
export type { FolderEntries } from './api/folder-types'
export type { ScopeFolderRows } from './api/folders'
export { globalSearch } from './api/mention-sources'
export type { GlobalSearchItem, GlobalSearchResult } from './api/search-types'
export { createProjectNote } from './memory-api'
export type { ProjectNoteReceipt } from './memory-api'

/** 前端提交审批决定（同意/拒绝高危工具调用） */
export function decideApproval(approvalId: string, approved: boolean, reason = ''): Promise<Record<string, unknown>> {
  return api.post(`agent/approval/${approvalId}/decide`, { json: { approved, reason } }).json<Record<string, unknown>>()
}

/**
 * 重生成 / 续写（`POST /agent/sessions/{id}/regenerate`，返回未消费的 SSE Response）。
 *
 * 与 {@link openMessageStream} 同形，所以复用同一条流消费链路；区别只在语义：
 * **不新落用户消息**（复用原提问）、轮次号不增、开流前服务端把这一轮同栏的旧回答
 * 标成 `metadata.superseded`（列表接口据此隐藏，行不删）。
 *
 * `from_message_id` 传的是**被操作那条消息的库主键**（`parseMessageId` 的结果）。
 */
export function openRegenerateStream(
  sessionId: string,
  body: { from_message_id: number; mode: 'regenerate' | 'continue'; agents?: string[] },
  signal?: AbortSignal,
): Promise<Response> {
  return api.post(`agent/sessions/${sessionId}/regenerate`, { json: body, signal })
}

/**
 * 发消息并返回未消费的 SSE Response（body 是 ReadableStream）。
 * ky 的 ResponsePromise 本身就是 Promise<Response>，await 即得原生 Response
 * （body 未消费，交给 store 读流）；非 2xx 会抛 HTTPError（SSE 端点恒 200，
 * 鉴权 401 由 ky 的 401 刷新钩子先行处理）。
 * `signal` 用于「停止生成」：中断即客户端断开，服务端会把已流出的
 * 部分回答落库（metadata.truncated），前端随后重拉历史即可对齐。
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

/**
 * qoder 登录态（`GET /agent/qoder/auth`）：只读服务端磁盘上的凭据文件，秒回。
 *
 * 为什么不复用 `fetchBackends()`：登录是一条**有状态流程**（点按钮 → 拿链接 →
 * 轮询结果），清单接口承载不了那个状态机（见后端 `qoder_auth_api` 的说明）。
 */
export function fetchQoderAuth(): Promise<QoderAuthState> {
  return api.get('agent/qoder/auth').json<QoderAuthState>()
}

/**
 * 发起一次 qoder 浏览器授权，返回授权链接（后端起 `qodercli login`）。
 *
 * `accountId` 空 = **往池子里加一个账号**（额度是账号级的，见 backend-types 的说明）；
 * 非空 = 给那个账号换令牌（登录失效后重登）。
 */
export function startQoderLogin(accountId = ''): Promise<QoderLoginState> {
  return api.post('agent/qoder/login', { json: { account_id: accountId } }).json<QoderLoginState>()
}

/** 轮询某次授权的状态；未知 id 返回 `state=expired`（后端不抛 404）。 */
export function fetchQoderLoginStatus(loginId: string): Promise<QoderLoginState> {
  return api.get(`agent/qoder/login/${loginId}`).json<QoderLoginState>()
}

/**
 * 平台模型（LLMProvider）在 qoder 里的接入状态。
 *
 * BYOK 是把自家网关接进 qoder 的**唯一**官方通道（CLI 是 `/model` → Custom，
 * SDK 是 `create_byok_config`）；接入后模型清单里会多出 `<provider_id>/<model>`。
 */
export function fetchQoderByok(): Promise<QoderByokState> {
  return api.get('agent/qoder/byok').json<QoderByokState>()
}

/** 一键把「AI 平台」里的网关注册成 qoder 的自定义 provider（幂等）。 */
export function registerQoderByok(): Promise<QoderByokState> {
  return api.post('agent/qoder/byok/platform').json<QoderByokState>()
}

/** 取消接入（删掉 qoder 的 settings.json 里那条 provider）。 */
export function deleteQoderByok(): Promise<QoderByokState> {
  return api.delete('agent/qoder/byok/platform').json<QoderByokState>()
}
