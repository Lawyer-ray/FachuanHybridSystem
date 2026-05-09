import type { StateCreator } from 'zustand'
import type { StreamingMessage, ApprovalState, SSEEvent } from '../types'
import * as api from '../api'
import { getAccessToken } from '@/lib/token'
import { API_BASE_URL } from '@/lib/api'
import { connectAndReadStream, reduceStreamingMessage } from './streaming-helpers'
import {
  createUserMessage,
  finalizeStreamingMessages,
  createAbortedMessage,
  createPartialMessage,
  createErrorMessage,
} from './message-factory'
import type { WorkbenchStore } from './workbench-store'

let _abortController: AbortController | null = null

export interface StreamingSlice {
  isStreaming: boolean
  streamingMessage: StreamingMessage | null
  reconnecting: boolean
  pendingApproval: ApprovalState | null
  quotedContent: string | null
  setQuotedContent: (content: string | null) => void
  sendMessage: (content: string) => Promise<void>
  editAndResend: (messageId: number, newContent: string) => Promise<void>
  submitFeedback: (messageId: number, rating: 'good' | 'bad') => Promise<void>
  abortStream: () => void
  handleSSEEvent: (event: SSEEvent) => void
  respondApproval: (approved: boolean) => Promise<void>
  resetStreaming: () => void
}

export const createStreamingSlice: StateCreator<WorkbenchStore, [], [], StreamingSlice> = (set, get) => ({
  isStreaming: false,
  streamingMessage: null,
  reconnecting: false,
  pendingApproval: null,
  quotedContent: null,
  setQuotedContent: (content) => set({ quotedContent: content }),

  sendMessage: async (content) => {
    const { currentSession, selectedModel, selectedAgent, attachments } = get()
    if (!currentSession) return

    const readyAttachments = attachments.filter((a) => a.status === 'ready')
    const attachmentIds = readyAttachments.map((a) => a.id)

    const attachmentNote =
      readyAttachments.length > 0
        ? `\n\n[附件: ${readyAttachments.map((a) => a.name).join(', ')}]`
        : ''
    const fullContent = content + attachmentNote

    get().appendMessages(createUserMessage(fullContent))

    _abortController = new AbortController()
    set({
      isStreaming: true,
      streamingMessage: { role: 'assistant', content: '', toolCalls: [], handoffs: [] },
    })

    let lastEventId = ''
    const MAX_RETRIES = 3
    let retryCount = 0

    const connectAndRead = async (resumeFrom: string): Promise<void> => {
      const token = getAccessToken()
      const url = `${API_BASE_URL}/workbench/sessions/${currentSession.id}/messages/stream`

      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      }
      if (resumeFrom) {
        headers['Last-Event-ID'] = resumeFrom
      }

      await connectAndReadStream(
        url,
        headers,
        {
          content: resumeFrom ? undefined : fullContent,
          llm_model: selectedModel,
          agent_type: selectedAgent,
          attachment_ids: resumeFrom ? undefined : (attachmentIds.length > 0 ? attachmentIds : undefined),
          resume_from: resumeFrom || undefined,
        },
        _abortController?.signal,
        (event) => {
          get().handleSSEEvent(event)
          retryCount = 0
        },
        (id) => { lastEventId = id },
      )
    }

    try {
      await connectAndRead('')

      const { streamingMessage } = get()
      const newMessages = finalizeStreamingMessages(streamingMessage)

      if (streamingMessage?.error && !streamingMessage.content) {
        newMessages.push(createErrorMessage(streamingMessage.error))
      }

      if (newMessages.length > 0) {
        get().appendMessages(...newMessages)
      }
    } catch (err) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        const { streamingMessage: sm } = get()
        if (sm && sm.content) {
          get().appendMessages(createAbortedMessage(sm.content, sm.model))
        }
      } else {
        const { streamingMessage: sm } = get()
        if (sm && sm.content && retryCount < MAX_RETRIES) {
          retryCount++
          const delay = Math.min(1000 * Math.pow(2, retryCount - 1), 8000)
          set({ reconnecting: true })

          try {
            await new Promise((r) => setTimeout(r, delay))
            if (!_abortController?.signal.aborted) {
              await connectAndRead(lastEventId)
              set({ reconnecting: false })
              return
            }
          } catch { /* 重连也失败 */ }
          set({ reconnecting: false })
        }

        const { streamingMessage: finalSm } = get()
        if (finalSm && finalSm.content) {
          get().appendMessages(createPartialMessage(finalSm.content, finalSm.model))
        } else {
          get().appendMessages(createErrorMessage(err instanceof Error ? err.message : '未知错误'))
        }
      }
    } finally {
      _abortController = null
      set({ isStreaming: false, streamingMessage: null, reconnecting: false, attachments: [] })
    }
  },

  editAndResend: async (messageId, newContent) => {
    const { currentSession, messages } = get()
    if (!currentSession) return

    const idx = messages.findIndex((m) => m.id === messageId)
    if (idx < 0) return

    try {
      await api.truncateMessages(currentSession.id, messageId)
    } catch { /* ignore */ }

    get().replaceMessages(messages.slice(0, idx))
    get().sendMessage(newContent)
  },

  submitFeedback: async (messageId, rating) => {
    try {
      await api.submitFeedback(messageId, rating)
      set((state) => ({
        messages: state.messages.map((m) =>
          m.id === messageId
            ? { ...m, metadata: { ...m.metadata, feedback: { rating } } }
            : m,
        ),
      }))
    } catch { /* ignore */ }
  },

  handleSSEEvent: (event) => {
    set((state) => {
      const sm = state.streamingMessage
      if (!sm) return state

      if (event.type === 'approval_request') {
        return {
          pendingApproval: {
            approvalId: event.approval_id || '',
            toolName: event.tool_name || '',
            toolArgs: event.tool_input || {},
          },
        }
      }

      return { streamingMessage: reduceStreamingMessage(sm, event) }
    })
  },

  abortStream: () => {
    if (_abortController) {
      _abortController.abort()
      _abortController = null
    }
  },

  respondApproval: async (approved) => {
    const { pendingApproval } = get()
    if (!pendingApproval) return
    try {
      await api.respondApproval(pendingApproval.approvalId, approved)
      set({ pendingApproval: null })
    } catch { /* ignore */ }
  },

  resetStreaming: () => {
    abortStreaming()
    set({
      isStreaming: false,
      streamingMessage: null,
      pendingApproval: null,
    })
  },
})

export function abortStreaming(): void {
  if (_abortController) {
    _abortController.abort()
    _abortController = null
  }
}
