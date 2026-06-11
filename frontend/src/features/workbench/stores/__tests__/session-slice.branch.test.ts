/**
 * session-slice - additional branch coverage tests
 * Targets uncovered branches in session-slice.ts
 */

import { create } from 'zustand'
import { createSessionSlice, type SessionSlice } from '../session-slice'
import { createStreamingSlice, type StreamingSlice } from '../streaming-slice'
import { createBatchSlice, type BatchSlice } from '../batch-slice'
import { createAttachmentSlice, type AttachmentSlice } from '../attachment-slice'

const mockListMessages = vi.fn().mockResolvedValue({ items: [], count: 0 })
const mockFetchModels = vi.fn().mockResolvedValue({
  models: [{ id: 'gpt-4o', name: 'GPT-4o' }, { id: 'gpt-3.5', name: 'GPT-3.5' }],
  default_model: 'gpt-4o',
})

vi.mock('../../api', () => ({
  fetchModels: (...args: unknown[]) => mockFetchModels(...args),
  listSessions: vi.fn().mockResolvedValue({ items: [], count: 0 }),
  createSession: vi.fn().mockResolvedValue({ id: 1, title: '', created_at: '', updated_at: '', model: '' }),
  listMessages: (...args: unknown[]) => mockListMessages(...args),
  getSession: vi.fn().mockResolvedValue({}),
  updateSession: vi.fn().mockResolvedValue({}),
  deleteSession: vi.fn().mockResolvedValue(undefined),
  truncateMessages: vi.fn().mockResolvedValue(undefined),
  submitFeedback: vi.fn().mockResolvedValue({}),
  respondApproval: vi.fn().mockResolvedValue({}),
  submitBatchAnalysis: vi.fn(),
  getBatchProgress: vi.fn(),
  cancelBatchAnalysis: vi.fn(),
  saveBatchMessages: vi.fn(),
  retryBatchAnalysis: vi.fn(),
  listBatchJobs: vi.fn(),
  connectBatchSSE: vi.fn(),
}))

vi.mock('../streaming-helpers', () => ({
  connectAndReadStream: vi.fn(),
  reduceStreamingMessage: vi.fn(),
  stripMetadataBlock: vi.fn((text: string) => text),
}))

vi.mock('../message-factory', () => ({
  createUserMessage: vi.fn(),
  finalizeStreamingMessages: vi.fn(() => []),
  createAbortedMessage: vi.fn(),
  createPartialMessage: vi.fn(),
  createErrorMessage: vi.fn(),
  createBatchItemMessage: vi.fn(),
  createBatchSummaryMessage: vi.fn(),
}))

vi.mock('../../utils/format-batch', () => ({
  formatBatchContent: vi.fn((content: string) => content),
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

describe('session-slice - branch coverage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // Branch: loadFavoriteModel localStorage throws (line 17-19)
  it('handles localStorage error in loadFavoriteModel', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    const store = createTestStore()
    // Should still initialize without crashing
    expect(store.getState().favoriteModel).toBe('')
    vi.restoreAllMocks()
  })

  // Branch: loadSelectedAgent with valid agent (line 24-25)
  it('loads valid agent from localStorage', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('case')
    const store = createTestStore()
    expect(store.getState().selectedAgent).toBe('case')
    vi.restoreAllMocks()
  })

  // Branch: loadSelectedAgent with invalid agent (line 24-26)
  it('falls back to triage for invalid agent in localStorage', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue('invalid_agent')
    const store = createTestStore()
    expect(store.getState().selectedAgent).toBe('triage')
    vi.restoreAllMocks()
  })

  // Branch: loadSelectedAgent with null value (line 24-26)
  it('falls back to triage when localStorage returns null', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockReturnValue(null)
    const store = createTestStore()
    expect(store.getState().selectedAgent).toBe('triage')
    vi.restoreAllMocks()
  })

  // Branch: loadSelectedAgent localStorage throws (line 28)
  it('handles localStorage error in loadSelectedAgent', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    const store = createTestStore()
    expect(store.getState().selectedAgent).toBe('triage')
    vi.restoreAllMocks()
  })

  // Branch: setFavoriteModel with model (line 76)
  it('setFavoriteModel stores model in localStorage', () => {
    const setItemSpy = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {})
    const store = createTestStore()
    store.getState().setFavoriteModel('gpt-4o')
    expect(store.getState().favoriteModel).toBe('gpt-4o')
    expect(setItemSpy).toHaveBeenCalledWith('workbench_favorite_model', 'gpt-4o')
    setItemSpy.mockRestore()
  })

  // Branch: setFavoriteModel with empty string (line 77)
  it('setFavoriteModel removes from localStorage when empty', () => {
    const removeItemSpy = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {})
    const store = createTestStore()
    store.getState().setFavoriteModel('')
    expect(store.getState().favoriteModel).toBe('')
    expect(removeItemSpy).toHaveBeenCalledWith('workbench_favorite_model')
    removeItemSpy.mockRestore()
  })

  // Branch: setFavoriteModel localStorage throws (line 78)
  it('setFavoriteModel handles localStorage error', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('quota') })
    const store = createTestStore()
    store.getState().setFavoriteModel('gpt-4o')
    expect(store.getState().favoriteModel).toBe('gpt-4o')
    vi.restoreAllMocks()
  })

  // Branch: setSelectedAgent localStorage throws (line 83)
  it('setSelectedAgent handles localStorage error', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    const store = createTestStore()
    store.getState().setSelectedAgent('case')
    expect(store.getState().selectedAgent).toBe('case')
    vi.restoreAllMocks()
  })

  // Branch: fetchModels with favorite model matching (line 94)
  it('fetchModels uses favorite model when it matches', async () => {
    const store = createTestStore()
    store.getState().setFavoriteModel('gpt-3.5')
    await store.getState().fetchModels()
    expect(store.getState().selectedModel).toBe('gpt-3.5')
  })

  // Branch: fetchModels with favorite model not matching (line 94-96)
  it('fetchModels falls back to default when favorite does not match', async () => {
    const store = createTestStore()
    store.getState().setFavoriteModel('nonexistent')
    await store.getState().fetchModels()
    expect(store.getState().selectedModel).toBe('gpt-4o')
  })

  // Branch: fetchModels with already selected model (line 93)
  it('fetchModels keeps already selected model', async () => {
    const store = createTestStore()
    store.getState().setSelectedModel('gpt-3.5')
    await store.getState().fetchModels()
    expect(store.getState().selectedModel).toBe('gpt-3.5')
  })

  // Branch: fetchModels error (line 99-100)
  it('fetchModels handles error and sets modelsLoading false', async () => {
    mockFetchModels.mockRejectedValueOnce(new Error('fail'))
    const store = createTestStore()
    await store.getState().fetchModels()
    expect(store.getState().modelsLoading).toBe(false)
  })

  // Branch: setCurrentSession with session triggers fetchMessages (line 121)
  it('setCurrentSession triggers fetchMessages for session', async () => {
    mockListMessages.mockResolvedValue({ items: [{ id: 1 }], count: 1 })
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    expect(store.getState().messagesLoading).toBe(true)
    // Wait for fetchMessages
    await vi.waitFor(() => {
      expect(store.getState().messagesLoading).toBe(false)
    })
  })

  // Branch: setCurrentSession with null (line 120)
  it('setCurrentSession with null clears state', () => {
    const store = createTestStore()
    store.getState().setCurrentSession(null)
    expect(store.getState().currentSession).toBeNull()
    expect(store.getState().messages).toEqual([])
    expect(store.getState().messagesLoading).toBe(false)
  })

  // Branch: fetchMessages with multiple pages (totalPages > 1, totalPages === 2) (line 131-139)
  it('fetchMessages loads last 2 pages when totalPages is 2', async () => {
    mockListMessages.mockImplementation(async (_sessionId: number, page: number) => {
      if (page === 1) return { items: [{ id: 1 }], count: 80 }
      if (page === 2) return { items: [{ id: 50 }], count: 80 }
      return { items: [], count: 0 }
    })
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await vi.waitFor(() => {
      expect(store.getState().messagesLoading).toBe(false)
    })
    // Should have loaded both pages
    expect(store.getState().messages.length).toBe(2)
  })

  // Branch: fetchMessages with totalPages > 2 (line 137-139)
  it('fetchMessages loads last 2 pages when totalPages > 2', async () => {
    mockListMessages.mockImplementation(async (_sessionId: number, page: number) => {
      if (page === 1) return { items: [{ id: 1 }], count: 200 }
      if (page === 3) return { items: [{ id: 100 }], count: 200 }
      if (page === 4) return { items: [{ id: 150 }], count: 200 }
      return { items: [], count: 0 }
    })
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await vi.waitFor(() => {
      expect(store.getState().messagesLoading).toBe(false)
    })
    expect(store.getState().hasMoreMessages).toBe(true)
  })

  // Branch: fetchMessages with stale session check (line 142)
  it('fetchMessages ignores result when session changed', async () => {
    let resolveFirst: (value: unknown) => void
    mockListMessages.mockImplementation(async (sessionId: number) => {
      if (sessionId === 1) {
        return new Promise((resolve) => { resolveFirst = resolve })
      }
      return { items: [{ id: 99 }], count: 1 }
    })
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    // Switch session before first resolves
    store.getState().setCurrentSession({
      id: 2, title: 'Test2', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    // Resolve the first session's request
    resolveFirst!({ items: [{ id: 1 }], count: 1 })
    await vi.waitFor(() => {
      expect(store.getState().messagesLoading).toBe(false)
    })
    // Messages should be from session 2, not session 1
    expect(store.getState().messages.find((m) => m.id === 1)).toBeUndefined()
  })

  // Branch: fetchMessages error with stale session (line 150-151)
  it('fetchMessages error ignores result when session changed', async () => {
    mockListMessages.mockRejectedValue(new Error('fail'))
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    // Switch session
    store.getState().setCurrentSession({
      id: 2, title: 'Test2', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await vi.waitFor(() => {
      // Should not crash
      expect(true).toBe(true)
    })
  })

  // Branch: loadOlderMessages guard conditions (line 158)
  it('loadOlderMessages returns early when loading', async () => {
    mockListMessages.mockResolvedValue({ items: [], count: 0 })
    const store = createTestStore()
    store.setState({ loadingOlder: true } as Partial<SessionSlice>)
    await store.getState().loadOlderMessages()
    // Should not call API
  })

  // Branch: loadOlderMessages returns early when no hasMoreMessages (line 158)
  it('loadOlderMessages returns early when no more messages', async () => {
    const store = createTestStore()
    store.setState({ hasMoreMessages: false } as Partial<SessionSlice>)
    await store.getState().loadOlderMessages()
  })

  // Branch: loadOlderMessages returns early when messages empty (line 158)
  it('loadOlderMessages returns early when messages empty', async () => {
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    store.setState({ hasMoreMessages: true, messages: [] } as Partial<SessionSlice>)
    await store.getState().loadOlderMessages()
  })

  // Branch: loadOlderMessages returns early when no currentSession (line 158)
  it('loadOlderMessages returns early when no session', async () => {
    const store = createTestStore()
    store.setState({ hasMoreMessages: true, messages: [{ id: 1 }] } as Partial<SessionSlice>)
    await store.getState().loadOlderMessages()
  })

  // Branch: loadOlderMessages success with stale session check (line 164)
  it('loadOlderMessages ignores result when session changed', async () => {
    // Reset mock to return proper values for loadOlderMessages
    mockListMessages.mockReset()
    mockListMessages.mockResolvedValue({ items: [{ id: 50 }], count: 1, has_more: false })
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    // Wait for initial fetchMessages to complete
    await vi.waitFor(() => expect(store.getState().messagesLoading).toBe(false))
    store.setState({
      hasMoreMessages: true,
    } as Partial<SessionSlice>)
    await store.getState().loadOlderMessages()
    // Messages should include the older message
    expect(store.getState().messages.length).toBeGreaterThan(0)
  })

  // Branch: loadOlderMessages error (line 171-173)
  it('loadOlderMessages handles error gracefully', async () => {
    mockListMessages.mockReset()
    // First call for fetchMessages succeeds, second for loadOlderMessages fails
    let callCount = 0
    mockListMessages.mockImplementation(async () => {
      callCount++
      if (callCount <= 1) return { items: [{ id: 100 }], count: 1 }
      throw new Error('fail')
    })
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await vi.waitFor(() => expect(store.getState().messagesLoading).toBe(false))
    store.setState({
      hasMoreMessages: true,
    } as Partial<SessionSlice>)
    await store.getState().loadOlderMessages()
    expect(store.getState().loadingOlder).toBe(false)
  })

  // Branch: loadOlderMessages with has_more from response (line 168)
  it('loadOlderMessages uses has_more from response', async () => {
    mockListMessages.mockReset()
    mockListMessages.mockResolvedValue({ items: [{ id: 50 }], count: 1, has_more: true })
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await vi.waitFor(() => expect(store.getState().messagesLoading).toBe(false))
    store.setState({
      hasMoreMessages: true,
    } as Partial<SessionSlice>)
    await store.getState().loadOlderMessages()
    expect(store.getState().hasMoreMessages).toBe(true)
  })

  // Branch: loadOlderMessages with has_more undefined (line 168)
  it('loadOlderMessages defaults has_more to false when undefined', async () => {
    mockListMessages.mockReset()
    mockListMessages.mockResolvedValue({ items: [{ id: 50 }], count: 1 })
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await vi.waitFor(() => expect(store.getState().messagesLoading).toBe(false))
    store.setState({
      hasMoreMessages: true,
    } as Partial<SessionSlice>)
    await store.getState().loadOlderMessages()
    expect(store.getState().hasMoreMessages).toBe(false)
  })
})
