/** 工作台状态管理 (Zustand) */

import { create, type StateCreator } from 'zustand'
import type {
  WorkbenchSession,
  WorkbenchMessage,
  LLMModel,
  AgentType,
} from '../types'
import * as api from '../api'
import { createStreamingSlice, type StreamingSlice, abortStreaming } from './streaming-slice'
import { createBatchSlice, type BatchSlice, cleanupBatchState } from './batch-slice'
import { createAttachmentSlice, type AttachmentSlice } from './attachment-slice'

const FAVORITE_MODEL_KEY = 'workbench_favorite_model'
const SELECTED_AGENT_KEY = 'workbench_selected_agent'

function loadFavoriteModel(): string {
  try {
    return localStorage.getItem(FAVORITE_MODEL_KEY) || ''
  } catch { return '' }
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

// ============================================================================
// Composed Store Type
// ============================================================================

export type WorkbenchStore = SessionSlice & StreamingSlice & BatchSlice & AttachmentSlice

// ============================================================================
// Session Slice (留在主文件)
// ============================================================================

interface SessionSlice {
  sessions: WorkbenchSession[]
  currentSession: WorkbenchSession | null
  messages: WorkbenchMessage[]
  messagesLoading: boolean
  models: LLMModel[]
  selectedModel: string
  favoriteModel: string
  modelsLoading: boolean
  selectedAgent: AgentType
  setSelectedModel: (model: string) => void
  setFavoriteModel: (model: string) => void
  setSelectedAgent: (agent: AgentType) => void
  fetchModels: () => Promise<void>
  fetchSessions: () => Promise<void>
  createSession: (title?: string) => Promise<WorkbenchSession>
  setCurrentSession: (session: WorkbenchSession | null) => void
  fetchMessages: (sessionId: number) => Promise<void>
  reset: () => void
}

const createSessionSlice: StateCreator<WorkbenchStore, [], [], SessionSlice> = (set, get) => ({
  sessions: [],
  currentSession: null,
  messages: [],
  messagesLoading: false,
  models: [],
  selectedModel: '',
  favoriteModel: loadFavoriteModel(),
  modelsLoading: false,
  selectedAgent: loadSelectedAgent(),

  setSelectedModel: (model) => set({ selectedModel: model }),

  setFavoriteModel: (model) => {
    try {
      if (model) localStorage.setItem(FAVORITE_MODEL_KEY, model)
      else localStorage.removeItem(FAVORITE_MODEL_KEY)
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
    if (session) get().fetchMessages(session.id)
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

  reset: () => {
    abortStreaming()
    cleanupBatchState()
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
})

export const useWorkbenchStore = create<WorkbenchStore>()((...args) => ({
  ...createSessionSlice(...args),
  ...createStreamingSlice(...args),
  ...createBatchSlice(...args),
  ...createAttachmentSlice(...args),
}))
