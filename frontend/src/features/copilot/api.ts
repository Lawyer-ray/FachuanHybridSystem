/**
 * Copilot API 客户端：会话 CRUD 与流式发消息。
 *
 * 对流式请求的说明：后端是 POST 返回 SSE（见 agent_api.send_message），
 * EventSource 发不了 POST 也带不了 JWT 头，所以走 ky 拿原生 Response，
 * 由调用方（store）读 resp.body 流。ky 实例同时给了 JWT 注入与 401 刷新重试。
 */

import { api } from '@/lib/api'

import type { AgentHistoryMessage, AgentSession } from './types'

export function listSessions(limit = 50): Promise<AgentSession[]> {
  return api.get('agent/sessions', { searchParams: { limit } }).json<AgentSession[]>()
}

export function createSession(title = ''): Promise<AgentSession> {
  return api.post('agent/sessions', { json: { title } }).json<AgentSession>()
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
