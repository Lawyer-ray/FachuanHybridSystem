import { create } from 'zustand'
import { createSessionSlice, type SessionSlice } from '../session-slice'
import { createStreamingSlice, type StreamingSlice } from '../streaming-slice'
import { createBatchSlice, type BatchSlice } from '../batch-slice'
import { createAttachmentSlice, type AttachmentSlice } from '../attachment-slice'

vi.mock('../../api', () => ({
  fetchModels: vi.fn().mockResolvedValue({
    models: [{ id: 'gpt-4o', name: 'GPT-4o' }, { id: 'gpt-3.5', name: 'GPT-3.5' }],
    default_model: 'gpt-4o',
  }),
  listSessions: vi.fn().mockResolvedValue({
    items: [{ id: 1, title: 'Session 1', created_at: '2025-01-01', updated_at: '2025-01-01', model: 'gpt-4o' }],
    count: 1,
  }),
  createSession: vi.fn().mockResolvedValue({
    id: 2, title: 'New Session', created_at: '2025-01-02', updated_at: '2025-01-02', model: 'gpt-4o',
  }),
  listMessages: vi.fn().mockResolvedValue({
    items: [{ id: 1, role: 'user', content: 'hi', created_at: '2025-01-01' }],
    count: 1,
  }),
  getSession: vi.fn().mockResolvedValue({}),
  updateSession: vi.fn().mockResolvedValue({}),
  deleteSession: vi.fn().mockResolvedValue(undefined),
  truncateMessages: vi.fn().mockResolvedValue(undefined),
  submitFeedback: vi.fn().mockResolvedValue({}),
  respondApproval: vi.fn().mockResolvedValue({}),
  submitBatchAnalysis: vi.fn().mockResolvedValue({}),
  getBatchProgress: vi.fn().mockResolvedValue({}),
  cancelBatchAnalysis: vi.fn().mockResolvedValue({}),
  saveBatchMessages: vi.fn().mockResolvedValue({}),
  retryBatchAnalysis: vi.fn().mockResolvedValue({}),
  listBatchJobs: vi.fn().mockResolvedValue({ items: [], count: 0 }),
  connectBatchSSE: vi.fn().mockReturnValue(() => {}),
}))

type TestStore = SessionSlice & StreamingSlice & BatchSlice & AttachmentSlice

function createTestStore() {
  return create<TestStore>()((...args) => ({
    ...createSessionSlice(...args),
    ...createStreamingSlice(...args),
    ...createBatchSlice(...args),
    ...createAttachmentSlice(...args),
  }))
}

describe('session-slice', () => {
  it('has initial empty sessions', () => {
    const store = createTestStore()
    expect(store.getState().sessions).toEqual([])
  })

  it('has initial null current session', () => {
    const store = createTestStore()
    expect(store.getState().currentSession).toBeNull()
  })

  it('has initial empty messages', () => {
    const store = createTestStore()
    expect(store.getState().messages).toEqual([])
  })

  it('sets current session', () => {
    const store = createTestStore()
    const session = { id: 1, title: 'Session 1', created_at: '2025-01-01T00:00:00Z', updated_at: '2025-01-01T00:00:00Z', model: 'gpt-4o' }
    store.getState().setCurrentSession(session)
    expect(store.getState().currentSession).toEqual(session)
  })

  it('appends messages', () => {
    const store = createTestStore()
    const msg = {
      id: 1, role: 'user' as const, content: 'Hello', created_at: '2025-01-01T00:00:00Z',
      llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {},
    }
    store.getState().appendMessages(msg)
    expect(store.getState().messages).toHaveLength(1)
    expect(store.getState().messages[0].content).toBe('Hello')
  })

  it('clears messages', () => {
    const store = createTestStore()
    store.getState().appendMessages({
      id: 1, role: 'user' as const, content: 'Hello', created_at: '2025-01-01T00:00:00Z',
      llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {},
    })
    store.getState().clearMessages()
    expect(store.getState().messages).toEqual([])
  })

  it('sets selected model', () => {
    const store = createTestStore()
    store.getState().setSelectedModel('gpt-4o')
    expect(store.getState().selectedModel).toBe('gpt-4o')
  })

  it('sets selected agent', () => {
    const store = createTestStore()
    store.getState().setSelectedAgent('default')
    expect(store.getState().selectedAgent).toBe('default')
  })

  it('resets session', () => {
    const store = createTestStore()
    store.getState().appendMessages({
      id: 1, role: 'user' as const, content: 'Hello', created_at: '2025-01-01T00:00:00Z',
      llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {},
    })
    store.getState().resetSession()
    expect(store.getState().messages).toEqual([])
    expect(store.getState().currentSession).toBeNull()
  })

  it('fetchModels sets models and selected model', async () => {
    const store = createTestStore()
    await store.getState().fetchModels()
    const state = store.getState()
    expect(state.models).toHaveLength(2)
    expect(state.selectedModel).toBe('gpt-4o')
    expect(state.modelsLoading).toBe(false)
  })

  it('fetchModels uses favorite model when available', async () => {
    const store = createTestStore()
    store.getState().setFavoriteModel('gpt-3.5')
    await store.getState().fetchModels()
    expect(store.getState().selectedModel).toBe('gpt-3.5')
  })

  it('fetchModels handles error gracefully', async () => {
    const { fetchModels } = await import('../../api')
    vi.mocked(fetchModels).mockRejectedValueOnce(new Error('network'))
    const store = createTestStore()
    await store.getState().fetchModels()
    expect(store.getState().modelsLoading).toBe(false)
  })

  it('fetchSessions populates sessions', async () => {
    const store = createTestStore()
    await store.getState().fetchSessions()
    expect(store.getState().sessions).toHaveLength(1)
    expect(store.getState().sessions[0].title).toBe('Session 1')
  })

  it('fetchSessions handles error gracefully', async () => {
    const { listSessions } = await import('../../api')
    vi.mocked(listSessions).mockRejectedValueOnce(new Error('fail'))
    const store = createTestStore()
    await store.getState().fetchSessions()
    expect(store.getState().sessions).toEqual([])
  })

  it('createSession creates and sets current session', async () => {
    const store = createTestStore()
    store.getState().setSelectedModel('gpt-4o')
    const session = await store.getState().createSession('Test')
    expect(session.title).toBe('New Session')
    expect(store.getState().currentSession).toEqual(session)
    expect(store.getState().sessions[0]).toEqual(session)
  })

  it('fetchMessages loads messages for session', async () => {
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Session', created_at: '2025-01-01', updated_at: '2025-01-01', model: 'gpt-4o',
    })
    await store.getState().fetchMessages(1)
    expect(store.getState().messages).toHaveLength(1)
    expect(store.getState().messagesLoading).toBe(false)
  })

  it('fetchMessages handles error gracefully', async () => {
    const { listMessages } = await import('../../api')
    vi.mocked(listMessages).mockRejectedValueOnce(new Error('fail'))
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Session', created_at: '2025-01-01', updated_at: '2025-01-01', model: 'gpt-4o',
    })
    await store.getState().fetchMessages(1)
    expect(store.getState().messagesLoading).toBe(false)
  })

  it('replaceMessages replaces all messages', () => {
    const store = createTestStore()
    store.getState().appendMessages({
      id: 1, role: 'user' as const, content: 'old', created_at: '2025-01-01T00:00:00Z',
      llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {},
    })
    const newMsgs = [{
      id: 2, role: 'assistant' as const, content: 'new', created_at: '2025-01-02T00:00:00Z',
      llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {},
    }]
    store.getState().replaceMessages(newMsgs)
    expect(store.getState().messages).toHaveLength(1)
    expect(store.getState().messages[0].content).toBe('new')
  })

  it('setFavoriteModel stores to localStorage', () => {
    const store = createTestStore()
    store.getState().setFavoriteModel('gpt-4o')
    expect(store.getState().favoriteModel).toBe('gpt-4o')
  })

  it('setFavoriteModel removes from localStorage when empty', () => {
    const store = createTestStore()
    store.getState().setFavoriteModel('gpt-4o')
    store.getState().setFavoriteModel('')
    expect(store.getState().favoriteModel).toBe('')
  })

  it('setSelectedAgent stores value', () => {
    const store = createTestStore()
    store.getState().setSelectedAgent('case')
    expect(store.getState().selectedAgent).toBe('case')
  })
})
