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

export async function saveBatchMessages(
  jobId: string,
  items: { file_name: string; content: string; metadata?: Record<string, unknown> }[],
): Promise<{ success: boolean; created_count: number }> {
  return api.post(`batch/${jobId}/messages`, { json: items }).json()
}

export async function retryBatchAnalysis(
  jobId: string,
): Promise<{ success: boolean; message: string; retry_count?: number }> {
  return api.post(`batch/${jobId}/retry`).json()
}

export async function listBatchJobs(
  sessionId: number,
  page = 1,
): Promise<{ items: BatchJob[]; count: number }> {
  return api.get(`sessions/${sessionId}/batch-jobs`, { searchParams: { page } }).json()
}

/**
 * 连接批量分析 SSE 流
 * 返回清理函数，调用后断开连接
 */
export function connectBatchSSE(
  jobId: string,
  onEvent: (event: { type: string; data: Record<string, unknown>; timestamp?: number }) => void,
  onDone: () => void,
  onError: (err: Error) => void,
): () => void {
  const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1'
  const token = localStorage.getItem('access_token')
  const controller = new AbortController()

  ;(async () => {
    try {
      const response = await fetch(`${baseUrl}/workbench/batch/${jobId}/stream`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        signal: controller.signal,
      })

      if (!response.ok) {
        throw new Error(`SSE 连接失败: HTTP ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No reader')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue
          const data = line.slice(6).trim()
          if (!data) continue

          try {
            const event = JSON.parse(data)
            if (event.type === 'done') {
              onDone()
              return
            }
            onEvent(event)
          } catch {
            /* skip malformed */
          }
        }
      }

      // Stream ended without done event
      onDone()
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') return
      onError(err instanceof Error ? err : new Error(String(err)))
    }
  })()

  return () => controller.abort()
}
