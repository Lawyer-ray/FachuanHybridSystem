/** 工作台 API 客户端 */

import { createApiClient } from '@/lib/api'
import type { BatchJob, BatchProgress, ModelsResponse, WorkbenchMessage, WorkbenchSession } from './types'

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

export async function submitFeedback(
  messageId: number,
  rating: 'good' | 'bad',
  comment = '',
): Promise<{ success: boolean; message: string }> {
  return api.patch(`messages/${messageId}/feedback`, { json: { rating, comment } }).json()
}

// ─── 审批 API ─────────────────────────────────────────────────────────────────

export async function respondApproval(approvalId: string, approved: boolean): Promise<{ success: boolean; message: string }> {
  return api.post('approval', { json: { approval_id: approvalId, approved } }).json()
}

// ─── 模型列表 API ─────────────────────────────────────────────────────────────

export async function fetchModels(): Promise<ModelsResponse> {
  return api.get('models').json()
}

// ─── 批量分析 API ────────────────────────────────────────────────────────────

export async function submitBatchAnalysis(
  sessionId: number,
  prompt: string,
  llmModel: string,
  files: File[],
  concurrency = 50,
): Promise<BatchJob> {
  const formData = new FormData()
  formData.append('session_id', String(sessionId))
  formData.append('prompt', prompt)
  formData.append('llm_model', llmModel)
  formData.append('concurrency', String(concurrency))
  for (const file of files) {
    formData.append('files', file)
  }
  return api.post('batch/analyze', { body: formData }).json()
}

export async function getBatchProgress(jobId: string): Promise<BatchProgress> {
  return api.get(`batch/${jobId}/progress`).json()
}

export async function cancelBatchAnalysis(jobId: string): Promise<{ success: boolean; status: string; message: string }> {
  return api.post(`batch/${jobId}/cancel`).json()
}
