/** 工作台 API 客户端 */

import { createApiClient } from '@/lib/api'
import type { ModelsResponse, WorkbenchMessage, WorkbenchSession } from './types'

const api = createApiClient({
  prefixUrl: `${import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1'}/workbench`,
})

// ─── 会话 API ────────────────────────────────────────────────────────────────

export async function createSession(title?: string, llmModel?: string): Promise<WorkbenchSession> {
  return api.post('sessions', { json: { title: title ?? '', llm_model: llmModel ?? '' } }).json()
}

export async function listSessions(page = 1): Promise<{ items: WorkbenchSession[]; count: number }> {
  return api.get('sessions', { searchParams: { page } }).json()
}

export async function getSession(sessionId: number): Promise<WorkbenchSession> {
  return api.get(`sessions/${sessionId}`).json()
}

export async function updateSession(
  sessionId: number,
  data: { title?: string; llm_model?: string; status?: string },
): Promise<WorkbenchSession> {
  return api.patch(`sessions/${sessionId}`, { json: data }).json()
}

export async function deleteSession(sessionId: number): Promise<void> {
  await api.delete(`sessions/${sessionId}`)
}

// ─── 消息 API ────────────────────────────────────────────────────────────────

export async function listMessages(
  sessionId: number,
  page = 1,
): Promise<{ items: WorkbenchMessage[]; count: number }> {
  return api.get(`sessions/${sessionId}/messages`, { searchParams: { page } }).json()
}

export async function truncateMessages(sessionId: number, fromMessageId: number): Promise<void> {
  await api.delete(`sessions/${sessionId}/messages/from/${fromMessageId}`)
}

// ─── 审批 API ─────────────────────────────────────────────────────────────────

export async function respondApproval(approvalId: string, approved: boolean): Promise<{ success: boolean; message: string }> {
  return api.post('approval', { json: { approval_id: approvalId, approved } }).json()
}

// ─── 模型列表 API ─────────────────────────────────────────────────────────────

export async function fetchModels(): Promise<ModelsResponse> {
  return api.get('models').json()
}
