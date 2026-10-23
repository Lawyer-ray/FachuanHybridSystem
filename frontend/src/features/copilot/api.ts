/**
 * Copilot API 客户端：会话 CRUD 与流式发消息。
 *
 * 对流式请求的说明：后端是 POST 返回 SSE（见 agent_api.send_message），
 * EventSource 发不了 POST 也带不了 JWT 头，所以走 ky 拿原生 Response，
 * 由调用方（store）读 resp.body 流。ky 实例同时给了 JWT 注入与 401 刷新重试。
 */

import { api } from '@/lib/api'

import type { AgentHistoryMessage, AgentSession, AgentTaskReceipt, CopilotScope, PendingApprovalItem, UsageSummary } from './types'

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

export function createSession(title = '', scope?: CopilotScope): Promise<AgentSession> {
  return api.post('agent/sessions', { json: { title, ...scopePayload(scope) } }).json<AgentSession>()
}

export function deleteSession(sessionId: string): Promise<{ deleted: number }> {
  return api.delete(`agent/sessions/${sessionId}`).json<{ deleted: number }>()
}

/** 重命名会话（侧边栏改名入口；空标题后端 400） */
export function renameSession(sessionId: string, title: string): Promise<AgentSession> {
  return api.patch(`agent/sessions/${sessionId}`, { json: { title } }).json<AgentSession>()
}

export function fetchHistory(sessionId: string, limit = 200): Promise<AgentHistoryMessage[]> {
  return api.get(`agent/sessions/${sessionId}/messages`, { searchParams: { limit } }).json<AgentHistoryMessage[]>()
}

/** 前端提交审批决定（同意/拒绝高危工具调用） */
export function decideApproval(approvalId: string, approved: boolean): Promise<Record<string, unknown>> {
  return api.post(`agent/approval/${approvalId}/decide`, { json: { approved } }).json<Record<string, unknown>>()
}

/**
 * 发消息并返回未消费的 SSE Response（body 是 ReadableStream）。
 * ky 的 ResponsePromise 本身就是 Promise<Response>，await 即得原生 Response
 * （body 未消费，交给 store 读流）；非 2xx 会抛 HTTPError（SSE 端点恒 200，
 * 鉴权 401 由 ky 的 401 刷新钩子先行处理）。
 * `signal` 用于「停止生成」：中断即客户端断开，服务端会把已流出的
 * 部分回答落库（metadata.truncated），前端随后重拉历史即可对齐。
 */
export function openMessageStream(sessionId: string, message: string, signal: AbortSignal): Promise<Response> {
  return api.post(`agent/sessions/${sessionId}/messages`, { json: { message }, signal })
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
