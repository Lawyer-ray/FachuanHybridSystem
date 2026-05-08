/** 工作台状态管理 (Zustand) */

import { create } from 'zustand'
import type {
  WorkbenchSession,
  WorkbenchMessage,
  LLMModel,
  AgentType,
  ApprovalState,
  SSEEvent,
  StreamingMessage,
  ToolCallState,
  BatchProgress,
  Attachment,
} from '../types'
import * as api from '../api'

const FAVORITE_MODEL_KEY = 'workbench_favorite_model'
const SELECTED_AGENT_KEY = 'workbench_selected_agent'

// 匹配【案例元数据汇总】块（兼容有无代码块包裹），用于前端展示时去除
const METADATA_BLOCK_RE = /```[^\n]*\n\s*【案例元数据汇总】\s*\n[\s\S]*?\n\s*```\s*$|【案例元数据汇总】\s*\n[\s\S]*$/g

/** 去除分析结果中的元数据汇总块，只保留分析正文 */
function stripMetadataBlock(text: string): string {
  return text.replace(METADATA_BLOCK_RE, '').trim()
}

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
    const userMsg: WorkbenchMessage = {
      id: Date.now(),
      role: 'user',
      content: fullContent,
      llm_model: '',
      tool_call_id: '',
      tool_name: '',
      tool_input: {},
      tool_output: {},
      metadata: {},
      created_at: new Date().toISOString(),
    }
    set((state) => ({ messages: [...state.messages, userMsg] }))

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
      const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1'
      const token = localStorage.getItem('access_token')
      const url = `${baseUrl}/workbench/sessions/${currentSession.id}/messages/stream`

      const headers: Record<string, string> = {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      }
      if (resumeFrom) {
        headers['Last-Event-ID'] = resumeFrom
      }

      const response = await fetch(url, {
        method: 'POST',
        signal: _abortController?.signal,
        headers,
        body: JSON.stringify({
          content: resumeFrom ? undefined : fullContent,
          llm_model: selectedModel,
          agent_type: selectedAgent,
          attachment_ids: resumeFrom ? undefined : (attachmentIds.length > 0 ? attachmentIds : undefined),
          resume_from: resumeFrom || undefined,
        }),
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
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
          if (data === '[DONE]') continue

          try {
            const event = JSON.parse(data) as SSEEvent
            // 跟踪事件 ID 用于重连
            if (event.type === 'meta' && event.session_id) {
              lastEventId = event.session_id
            }
            get().handleSSEEvent(event)
            retryCount = 0 // 成功接收事件后重置重试计数
          } catch { /* skip malformed */ }
        }
      }
    }

    try {
      await connectAndRead('')

      // 流结束 - 将 streamingMessage 转为正式消息
      const { streamingMessage } = get()
      const newMessages: WorkbenchMessage[] = []

      // 保存工具调用消息
      if (streamingMessage) {
        for (const tc of streamingMessage.toolCalls) {
          newMessages.push({
            id: Date.now() + Math.random(),
            role: 'tool',
            content: `工具 ${tc.name}: ${tc.status === 'success' ? '成功' : tc.status === 'error' ? '失败' : '执行中'}`,
            llm_model: '',
            tool_call_id: tc.toolCallId,
            tool_name: tc.name,
            tool_input: tc.arguments,
            tool_output: tc.result ? { result: tc.result, success: tc.success } : {},
            metadata: { success: tc.success ?? (tc.status === 'success') },
            created_at: new Date().toISOString(),
          })
        }
      }

      if (streamingMessage && streamingMessage.content) {
        newMessages.push({
          id: Date.now() + 1,
          role: 'assistant',
          content: streamingMessage.content,
          llm_model: streamingMessage.model || '',
          tool_call_id: '',
          tool_name: '',
          tool_input: {},
          tool_output: {},
          metadata: {},
          created_at: new Date().toISOString(),
        })
      }

      // 如果有错误信息但没有内容，显示错误消息
      if (streamingMessage?.error && !streamingMessage.content) {
        newMessages.push({
          id: Date.now() + 1,
          role: 'assistant',
          content: `请求失败: ${streamingMessage.error}`,
          llm_model: '',
          tool_call_id: '',
          tool_name: '',
          tool_input: {},
          tool_output: {},
          metadata: { error: true },
          created_at: new Date().toISOString(),
        })
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
          const partialMsg: WorkbenchMessage = {
            id: Date.now() + 1,
            role: 'assistant',
            content: sm.content + '\n\n[已中断]',
            llm_model: sm.model || '',
            tool_call_id: '',
            tool_name: '',
            tool_input: {},
            tool_output: {},
            metadata: { aborted: true },
            created_at: new Date().toISOString(),
          }
          set((state) => ({ messages: [...state.messages, partialMsg] }))
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
          const partialMsg: WorkbenchMessage = {
            id: Date.now() + 1,
            role: 'assistant',
            content: finalSm.content + '\n\n[连接中断，部分内容已保留]',
            llm_model: finalSm.model || '',
            tool_call_id: '',
            tool_name: '',
            tool_input: {},
            tool_output: {},
            metadata: { partial: true },
            created_at: new Date().toISOString(),
          }
          set((state) => ({ messages: [...state.messages, partialMsg] }))
        } else {
          const errorMsg: WorkbenchMessage = {
            id: Date.now() + 1,
            role: 'assistant',
            content: `请求失败: ${err instanceof Error ? err.message : '未知错误'}`,
            llm_model: '',
            tool_call_id: '',
            tool_name: '',
            tool_input: {},
            tool_output: {},
            metadata: {},
            created_at: new Date().toISOString(),
          }
          set((state) => ({ messages: [...state.messages, errorMsg] }))
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

      switch (event.type) {
        case 'meta':
          return {
            streamingMessage: {
              ...sm,
              model: event.model,
              activeAgent: event.agent || sm.activeAgent,
              currentActivity: event.agent ? `${event.agent} 正在思考...` : sm.currentActivity,
            },
          }

        case 'activity':
          return {
            streamingMessage: {
              ...sm,
              activeAgent: event.agent || sm.activeAgent,
              currentActivity: event.status === 'thinking'
                ? `${event.agent || sm.activeAgent || '助手'} 正在思考...`
                : sm.currentActivity,
            },
          }

        case 'delta':
          return {
            streamingMessage: {
              ...sm,
              content: sm.content + (event.content || ''),
              // 收到 delta 时清除 thinking 状态
              currentActivity: undefined,
            },
          }

        case 'tool_call': {
          const tc: ToolCallState = {
            toolCallId: event.tool_call_id || '',
            name: event.name || event.tool_name || '',
            arguments: event.arguments || event.tool_input || {},
            status: 'running',
          }
          const toolName = event.name || event.tool_name || '工具'
          return {
            streamingMessage: {
              ...sm,
              toolCalls: [...sm.toolCalls, tc],
              currentActivity: `正在执行 ${toolName}...`,
            },
          }
        }

        case 'tool_result': {
          const toolCallId = event.tool_call_id || ''
          return {
            streamingMessage: {
              ...sm,
              toolCalls: sm.toolCalls.map((tc) =>
                tc.toolCallId === toolCallId
                  ? {
                      ...tc,
                      result: event.result ?? event.tool_output,
                      success: event.success,
                      status: event.success === false ? 'error' as const : 'success' as const,
                    }
                  : tc,
              ),
              // 工具完成，清除活动状态（下一个 tool_call 或 delta 会重新设置）
              currentActivity: undefined,
            },
          }
        }

        case 'handoff':
          return {
            streamingMessage: {
              ...sm,
              handoffs: [
                ...sm.handoffs,
                { from: event.from_agent || '', to: event.to_agent || '' },
              ],
              currentActivity: `切换到 ${event.to_agent || '助手'}...`,
            },
          }

        case 'approval_request':
          return {
            pendingApproval: {
              approvalId: event.approval_id || '',
              toolName: event.tool_name || '',
              toolArgs: event.tool_input || {},
            },
          }

        case 'error':
          return {
            streamingMessage: {
              ...sm,
              error: event.message || '未知错误',
            },
          }

        default:
          return state
      }
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
        const summaryMsg: WorkbenchMessage = {
          id: Date.now() + 1,
          role: 'assistant',
          content: progress.job.summary,
          llm_model: '',
          tool_call_id: '',
          tool_name: '',
          tool_input: {},
          tool_output: {},
          metadata: { source: 'batch_analysis', job_id: progress.job.id },
          created_at: new Date().toISOString(),
        }

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
          messages: [...state.messages, summaryMsg],
          batchProgress: null,
        }))
      }
    }

    // 注入完成的 item 为消息
    const injectCompletedItem = (itemId: string, fileName: string, result: string, jobId: string) => {
      if (_shownBatchItemIds.has(itemId)) return
      _shownBatchItemIds.add(itemId)
      const msg: WorkbenchMessage = {
        id: Date.now() + Math.random(),
        role: 'assistant',
        content: `### ${fileName}\n\n${stripMetadataBlock(result)}`,
        llm_model: '',
        tool_call_id: '',
        tool_name: '',
        tool_input: {},
        tool_output: {},
        metadata: { source: 'batch_item', job_id: jobId },
        created_at: new Date().toISOString(),
      }
      set((state) => ({ messages: [...state.messages, msg] }))
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
      const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1'
      const token = localStorage.getItem('access_token')
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
