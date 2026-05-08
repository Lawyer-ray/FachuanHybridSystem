/** 工作台状态管理 (Zustand) */

import { create } from 'zustand'
import type {
  WorkbenchSession,
  WorkbenchMessage,
  LLMModel,
  AgentType,
  ApprovalState,
  StreamingMessage,
  BatchProgress,
  Attachment,
} from '../types'
import * as api from '../api'
import { getAccessToken } from '@/lib/token'
import { API_BASE_URL } from '@/lib/api'
import { connectAndReadStream, reduceStreamingMessage, stripMetadataBlock } from './streaming-helpers'
import {
  createUserMessage,
  finalizeStreamingMessages,
  createAbortedMessage,
  createPartialMessage,
  createErrorMessage,
  createBatchItemMessage,
  createBatchSummaryMessage,
} from './message-factory'

const FAVORITE_MODEL_KEY = 'workbench_favorite_model'
const SELECTED_AGENT_KEY = 'workbench_selected_agent'

// 用于中断正在进行的流式请求
let _abortController: AbortController | null = null
// 跟踪已展示的批量分析 item ID，避免重复注入消息
let _shownBatchItemIds: Set<string> = new Set()
// SSE 连接清理函数
let _cleanupBatchSSE: (() => void) | null = null

function loadFavoriteModel(): string {
  try {
    return localStorage.getItem(FAVORITE_MODEL_KEY) || ''
  } catch {
    return ''
  }
}

function loadSelectedAgent(): AgentType {
  try {
    const val = localStorage.getItem(SELECTED_AGENT_KEY)
    if (val && ['triage', 'case', 'contract', 'research'].includes(val)) {
      return val as AgentType
    }
  } catch { /* ignore */ }
  return 'triage'
}

interface WorkbenchState {
  // 会话
  sessions: WorkbenchSession[]
  currentSession: WorkbenchSession | null
  messages: WorkbenchMessage[]

  // 模型
  models: LLMModel[]
  selectedModel: string
  favoriteModel: string
  modelsLoading: boolean

  // Agent
  selectedAgent: AgentType

  // 消息加载
  messagesLoading: boolean

  // 流式状态
  isStreaming: boolean
  streamingMessage: StreamingMessage | null
  reconnecting: boolean

  // 审批
  pendingApproval: ApprovalState | null

  // 引用回复
  quotedContent: string | null
  setQuotedContent: (content: string | null) => void

  // 批量分析
  activeBatchJobId: string | null
  batchProgress: BatchProgress | null
  batchPolling: boolean

  // 上下文附件
  attachments: Attachment[]
  addAttachment: (file: File) => Promise<void>
  removeAttachment: (id: string) => void
  clearAttachments: () => void

  // Actions
  setSelectedModel: (model: string) => void
  setFavoriteModel: (model: string) => void
  setSelectedAgent: (agent: AgentType) => void
  fetchModels: () => Promise<void>
  fetchSessions: () => Promise<void>
  createSession: (title?: string) => Promise<WorkbenchSession>
  setCurrentSession: (session: WorkbenchSession | null) => void
  fetchMessages: (sessionId: number) => Promise<void>
  sendMessage: (content: string) => Promise<void>
  editAndResend: (messageId: number, newContent: string) => Promise<void>
  submitFeedback: (messageId: number, rating: 'good' | 'bad') => Promise<void>
  abortStream: () => void
  handleSSEEvent: (event: SSEEvent) => void
  respondApproval: (approved: boolean) => Promise<void>
  submitBatchAnalysis: (prompt: string, files: File[]) => Promise<void>
  cancelBatchAnalysis: () => Promise<void>
  reset: () => void
}

export const useWorkbenchStore = create<WorkbenchState>()((set, get) => ({
  sessions: [],
  currentSession: null,
  messages: [],
  models: [],
  selectedModel: '',
  favoriteModel: loadFavoriteModel(),
  modelsLoading: false,
  selectedAgent: loadSelectedAgent(),
  messagesLoading: false,
  isStreaming: false,
  streamingMessage: null,
  reconnecting: false,
  pendingApproval: null,
  quotedContent: null,
  setQuotedContent: (content) => set({ quotedContent: content }),
  activeBatchJobId: null,
  batchProgress: null,
  batchPolling: false,
  attachments: [],

  setSelectedModel: (model) => set({ selectedModel: model }),

  setFavoriteModel: (model) => {
    try {
      if (model) {
        localStorage.setItem(FAVORITE_MODEL_KEY, model)
      } else {
        localStorage.removeItem(FAVORITE_MODEL_KEY)
      }
    } catch { /* ignore */ }
    set({ favoriteModel: model })
  },

  setSelectedAgent: (agent) => {
    try { localStorage.setItem(SELECTED_AGENT_KEY, agent) } catch { /* ignore */ }
    set({ selectedAgent: agent })
  },

  fetchModels: async () => {
    set({ modelsLoading: true })
    try {
      const res = await api.fetchModels()
      const { selectedModel, favoriteModel } = get()
      let model = selectedModel
      if (!model) {
        model = favoriteModel && res.models.some((m) => m.id === favoriteModel)
          ? favoriteModel
          : res.default_model
      }
      set({ models: res.models, selectedModel: model, modelsLoading: false })
    } catch {
      set({ modelsLoading: false })
    }
  },

  fetchSessions: async () => {
    try {
      const res = await api.listSessions()
      set({ sessions: res.items })
    } catch { /* ignore */ }
  },

  createSession: async (title) => {
    const { selectedModel } = get()
    const session = await api.createSession(title, selectedModel)
    set((state) => ({ sessions: [session, ...state.sessions], currentSession: session, messages: [] }))
    return session
  },

  setCurrentSession: (session) => {
    set({ currentSession: session, messages: [], messagesLoading: !!session })
    if (session) {
      get().fetchMessages(session.id)
    }
  },

  fetchMessages: async (sessionId) => {
    set({ messagesLoading: true })
    try {
      const PAGE_SIZE = 50
      const first = await api.listMessages(sessionId, 1)
      let allItems = first.items
      const totalPages = Math.ceil(first.count / PAGE_SIZE)
      if (totalPages > 1) {
        const rest = await Promise.all(
          Array.from({ length: totalPages - 1 }, (_, i) => api.listMessages(sessionId, i + 2)),
        )
        allItems = [...allItems, ...rest.flatMap((r) => r.items)]
      }
      set({ messages: allItems, messagesLoading: false })
    } catch {
      set({ messagesLoading: false })
    }
  },

  sendMessage: async (content) => {
    const { currentSession, selectedModel, selectedAgent, attachments } = get()
    if (!currentSession) return

    // 收集已就绪的附件 ID
    const readyAttachments = attachments.filter((a) => a.status === 'ready')
    const attachmentIds = readyAttachments.map((a) => a.id)

    // 在用户消息中附加文件信息
    const attachmentNote =
      readyAttachments.length > 0
        ? `\n\n[附件: ${readyAttachments.map((a) => a.name).join(', ')}]`
        : ''
    const fullContent = content + attachmentNote

    // 添加用户消息到本地
    set((state) => ({ messages: [...state.messages, createUserMessage(fullContent)] }))

    // 开始流式请求
    _abortController = new AbortController()
    set({
      isStreaming: true,
      streamingMessage: { role: 'assistant', content: '', toolCalls: [], handoffs: [] },
    })

    // 可恢复流：记录最后事件 ID，支持断线重连
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

      // 流结束 - 将 streamingMessage 转为正式消息
      const { streamingMessage } = get()
      let newMessages = finalizeStreamingMessages(streamingMessage)

      // 如果有错误信息但没有内容，显示错误消息
      if (streamingMessage?.error && !streamingMessage.content) {
        newMessages.push(createErrorMessage(streamingMessage.error))
      }

      if (newMessages.length > 0) {
        set((state) => ({ messages: [...state.messages, ...newMessages] }))
      }
    } catch (err) {
      // 用户主动中断不显示错误
      if (err instanceof DOMException && err.name === 'AbortError') {
        // 中断时保留已有的流式内容
        const { streamingMessage: sm } = get()
        if (sm && sm.content) {
          set((state) => ({ messages: [...state.messages, createAbortedMessage(sm.content, sm.model)] }))
        }
      } else {
        // 尝试断线重连
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
          } catch {
            // 重连也失败
          }
          set({ reconnecting: false })
        }

        // 保留已收到的部分内容或显示错误
        const { streamingMessage: finalSm } = get()
        if (finalSm && finalSm.content) {
          set((state) => ({ messages: [...state.messages, createPartialMessage(finalSm.content, finalSm.model)] }))
        } else {
          set((state) => ({ messages: [...state.messages, createErrorMessage(err instanceof Error ? err.message : '未知错误')] }))
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

    // 找到该消息位置，截断后续消息
    const idx = messages.findIndex((m) => m.id === messageId)
    if (idx < 0) return

    // 删除该消息及之后的所有消息（后端）
    try {
      await api.truncateMessages(currentSession.id, messageId)
    } catch { /* ignore */ }

    // 更新本地状态：保留该消息之前的消息
    set({ messages: messages.slice(0, idx) })

    // 用新内容重新发送
    get().sendMessage(newContent)
  },

  submitFeedback: async (messageId, rating) => {
    try {
      await api.submitFeedback(messageId, rating)
      // 更新本地消息 metadata
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

      // approval_request 不属于 streamingMessage
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

  submitBatchAnalysis: async (prompt, files) => {
    const { currentSession, selectedModel } = get()
    if (!currentSession) return

    // 清理之前的 SSE 连接
    if (_cleanupBatchSSE) {
      _cleanupBatchSSE()
      _cleanupBatchSSE = null
    }

    _shownBatchItemIds = new Set()
    const job = await api.submitBatchAnalysis(currentSession.id, prompt, selectedModel, files)
    set({
      activeBatchJobId: job.id,
      batchProgress: { job, items: [], failed_items_detail: [] },
      batchPolling: true,
    })

    // 处理终态的通用逻辑
    const handleTerminal = async (progress: BatchProgress) => {
      set({ batchPolling: false })

      // 持久化批量分析结果到后端
      const completedItems = progress.items.filter(
        (item) => item.status === 'completed' && item.result,
      )
      if (completedItems.length > 0) {
        try {
          await api.saveBatchMessages(
            progress.job.id,
            completedItems.map((item) => ({
              file_name: item.file_name,
              content: `### ${item.file_name}\n\n${stripMetadataBlock(item.result)}`,
              metadata: { source: 'batch_item', job_id: progress.job.id },
            })),
          )
        } catch {
          // 持久化失败不影响用户体验
        }
      }

      // 完成时将汇总报告插入对话
      if (progress.job.status === 'completed' && progress.job.summary) {
        try {
          await api.saveBatchMessages(progress.job.id, [{
            file_name: '汇总报告',
            content: progress.job.summary,
            metadata: { source: 'batch_analysis', job_id: progress.job.id },
          }])
        } catch {
          // 持久化失败不影响用户体验
        }

        set((state) => ({
          messages: [...state.messages, createBatchSummaryMessage(progress.job.summary, progress.job.id)],
          batchProgress: null,
        }))
      }
    }

    // 注入完成的 item 为消息
    const injectCompletedItem = (itemId: string, fileName: string, result: string, jobId: string) => {
      if (_shownBatchItemIds.has(itemId)) return
      _shownBatchItemIds.add(itemId)
      set((state) => ({ messages: [...state.messages, createBatchItemMessage(fileName, stripMetadataBlock(result), jobId)] }))
    }

    // 尝试 SSE 连接
    _cleanupBatchSSE = api.connectBatchSSE(
      job.id,
      // onEvent
      (event) => {
        const { batchProgress } = get()
        if (!batchProgress) return

        if (event.type === 'item_completed') {
          // SSE 事件触发进度更新，完整结果通过 onDone 获取
          // 更新进度
          set({
            batchProgress: {
              ...batchProgress,
              job: {
                ...batchProgress.job,
                completed_items: (batchProgress.job.completed_items || 0) + 1,
              },
            },
          })
        } else if (event.type === 'item_failed') {
          set({
            batchProgress: {
              ...batchProgress,
              job: {
                ...batchProgress.job,
                failed_items: (batchProgress.job.failed_items || 0) + 1,
              },
            },
          })
        } else if (event.type === 'progress') {
          const data = event.data
          set({
            batchProgress: {
              ...batchProgress,
              job: {
                ...batchProgress.job,
                completed_items: data.completed_items as number,
                failed_items: data.failed_items as number,
                total_items: data.total_items as number,
                progress: data.progress as number,
              },
            },
          })
        }
      },
      // onDone - 终态，获取完整数据
      async () => {
        try {
          const progress = await api.getBatchProgress(job.id)
          set({ batchProgress: progress })

          // 注入完成的 items
          for (const item of progress.items) {
            if (item.status === 'completed' && item.result) {
              injectCompletedItem(item.id, item.file_name, item.result, progress.job.id)
            }
          }

          await handleTerminal(progress)
        } catch {
          set({ batchPolling: false })
        }
      },
      // onError - SSE 失败，回退到轮询
      () => {
        _cleanupBatchSSE = null
        // 回退到自适应轮询
        const poll = async () => {
          const { activeBatchJobId, batchPolling } = get()
          if (!activeBatchJobId || !batchPolling) return

          try {
            const progress = await api.getBatchProgress(activeBatchJobId)
            set({ batchProgress: progress })

            // 注入新完成的 items
            for (const item of progress.items) {
              if (item.status === 'completed' && item.result) {
                injectCompletedItem(item.id, item.file_name, item.result, progress.job.id)
              }
            }

            if (['completed', 'failed', 'cancelled'].includes(progress.job.status)) {
              await handleTerminal(progress)
              return
            }
          } catch {
            // 轮询失败不停止
          }

          // 自适应间隔
          const { batchProgress: bp } = get()
          const p = bp?.job.progress ?? 0
          const interval = p > 80 ? 5000 : 2000
          setTimeout(poll, interval)
        }
        setTimeout(poll, 2000)
      },
    )
  },

  cancelBatchAnalysis: async () => {
    const { activeBatchJobId } = get()
    if (!activeBatchJobId) return
    try {
      await api.cancelBatchAnalysis(activeBatchJobId)
      // 轮询会自动更新状态
    } catch { /* ignore */ }
  },

  addAttachment: async (file: File) => {
    const id = `att_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`
    const attachment: Attachment = {
      id,
      name: file.name,
      type: file.type,
      size: file.size,
      status: 'uploading',
    }
    set((s) => ({ attachments: [...s.attachments, attachment] }))

    try {
      // 尝试上传文件到后端
      const formData = new FormData()
      formData.append('file', file)
      const baseUrl = API_BASE_URL
      const token = getAccessToken()
      const resp = await fetch(`${baseUrl}/workbench/attachments`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: formData,
      })

      if (!resp.ok) throw new Error(`上传失败: ${resp.status}`)

      const data = await resp.json() as { id: string; url?: string }
      set((s) => ({
        attachments: s.attachments.map((a) =>
          a.id === id ? { ...a, status: 'ready' as const, url: data.url, id: data.id || id } : a,
        ),
      }))
    } catch {
      // 后端 API 未就绪时，回退到本地 base64 存储
      try {
        const reader = new FileReader()
        const dataUrl = await new Promise<string>((resolve, reject) => {
          reader.onload = () => resolve(reader.result as string)
          reader.onerror = reject
          reader.readAsDataURL(file)
        })
        set((s) => ({
          attachments: s.attachments.map((a) =>
            a.id === id ? { ...a, status: 'ready' as const, url: dataUrl } : a,
          ),
        }))
      } catch {
        set((s) => ({
          attachments: s.attachments.map((a) =>
            a.id === id ? { ...a, status: 'error' as const, error: '文件读取失败' } : a,
          ),
        }))
      }
    }
  },

  removeAttachment: (id: string) => {
    set((s) => ({ attachments: s.attachments.filter((a) => a.id !== id) }))
  },

  clearAttachments: () => {
    set({ attachments: [] })
  },

  reset: () => {
    // 重置时也中断进行中的请求
    if (_abortController) {
      _abortController.abort()
      _abortController = null
    }
    if (_cleanupBatchSSE) {
      _cleanupBatchSSE()
      _cleanupBatchSSE = null
    }
    _shownBatchItemIds = new Set()
    set({
      currentSession: null,
      messages: [],
      messagesLoading: false,
      isStreaming: false,
      streamingMessage: null,
      pendingApproval: null,
      activeBatchJobId: null,
      batchProgress: null,
      batchPolling: false,
      attachments: [],
    })
  },
}))
