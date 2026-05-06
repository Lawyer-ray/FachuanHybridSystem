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
} from '../types'
import * as api from '../api'

const FAVORITE_MODEL_KEY = 'workbench_favorite_model'
const SELECTED_AGENT_KEY = 'workbench_selected_agent'

// 用于中断正在进行的流式请求
let _abortController: AbortController | null = null

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
    if (val && ['triage', 'case', 'contract', 'research', 'general'].includes(val)) {
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

  // 审批
  pendingApproval: ApprovalState | null

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
  pendingApproval: null,

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
      const res = await api.listMessages(sessionId)
      set({ messages: res.items, messagesLoading: false })
    } catch {
      set({ messagesLoading: false })
    }
  },

  sendMessage: async (content) => {
    const { currentSession, selectedModel, selectedAgent } = get()
    if (!currentSession) return

    // 添加用户消息到本地
    const userMsg: WorkbenchMessage = {
      id: Date.now(),
      role: 'user',
      content,
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

    try {
      const baseUrl = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8002/api/v1'
      const token = localStorage.getItem('access_token')
      const url = `${baseUrl}/workbench/sessions/${currentSession.id}/messages/stream`

      const response = await fetch(url, {
        method: 'POST',
        signal: _abortController.signal,
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          content,
          llm_model: selectedModel,
          agent_type: selectedAgent,
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
            get().handleSSEEvent(event)
          } catch { /* skip malformed */ }
        }
      }

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
    } finally {
      _abortController = null
      set({ isStreaming: false, streamingMessage: null })
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

  reset: () => {
    // 重置时也中断进行中的请求
    if (_abortController) {
      _abortController.abort()
      _abortController = null
    }
    set({
      currentSession: null,
      messages: [],
      messagesLoading: false,
      isStreaming: false,
      streamingMessage: null,
      pendingApproval: null,
    })
  },
}))
