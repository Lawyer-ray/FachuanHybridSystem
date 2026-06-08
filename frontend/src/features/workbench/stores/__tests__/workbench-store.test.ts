import { create } from 'zustand'
import { createSessionSlice } from '../session-slice'
import { createStreamingSlice } from '../streaming-slice'
import { createBatchSlice, cleanupBatchState } from '../batch-slice'
import { createAttachmentSlice } from '../attachment-slice'
import type { WorkbenchStore } from '../workbench-store'

vi.mock('../../api', () => ({
  fetchModels: vi.fn().mockResolvedValue({ models: [], default_model: '' }),
  listSessions: vi.fn().mockResolvedValue({ items: [], count: 0 }),
  createSession: vi.fn().mockResolvedValue({ id: 1, title: '', created_at: '', updated_at: '', model: '' }),
  listMessages: vi.fn().mockResolvedValue({ items: [], count: 0 }),
  getSession: vi.fn().mockResolvedValue({}),
  updateSession: vi.fn().mockResolvedValue({}),
  deleteSession: vi.fn().mockResolvedValue(undefined),
  truncateMessages: vi.fn().mockResolvedValue(undefined),
  submitFeedback: vi.fn().mockResolvedValue({}),
  respondApproval: vi.fn().mockResolvedValue({}),
  submitBatchAnalysis: vi.fn().mockResolvedValue({ id: 'job-1', status: 'running', total_items: 0, completed_items: 0, failed_items: 0, progress: 0 }),
  getBatchProgress: vi.fn().mockResolvedValue({ job: { id: 'job-1', status: 'completed', total_items: 1, completed_items: 1, failed_items: 0, progress: 100, summary: '' }, items: [], failed_items_detail: [] }),
  cancelBatchAnalysis: vi.fn().mockResolvedValue({}),
  saveBatchMessages: vi.fn().mockResolvedValue({}),
  retryBatchAnalysis: vi.fn().mockResolvedValue({}),
  listBatchJobs: vi.fn().mockResolvedValue({ items: [], count: 0 }),
  connectBatchSSE: vi.fn().mockReturnValue(() => {}),
}))

function createTestStore() {
  return create<WorkbenchStore>()((...args) => ({
    ...createSessionSlice(...args),
    ...createStreamingSlice(...args),
    ...createBatchSlice(...args),
    ...createAttachmentSlice(...args),
  }))
}

describe('workbench-store', () => {
  it('creates store with all slices', () => {
    const store = createTestStore()
    const state = store.getState()
    expect(state).toHaveProperty('sessions')
    expect(state).toHaveProperty('messages')
    expect(state).toHaveProperty('isStreaming')
    expect(state).toHaveProperty('attachments')
  })

  it('has initial empty sessions', () => {
    const store = createTestStore()
    expect(store.getState().sessions).toEqual([])
  })

  it('has initial empty messages', () => {
    const store = createTestStore()
    expect(store.getState().messages).toEqual([])
  })

  it('isStreaming is false by default', () => {
    const store = createTestStore()
    expect(store.getState().isStreaming).toBe(false)
  })

  it('has initial empty attachments', () => {
    const store = createTestStore()
    expect(store.getState().attachments).toEqual([])
  })

  it('currentSession is null by default', () => {
    const store = createTestStore()
    expect(store.getState().currentSession).toBeNull()
  })

  it('batchProgress is null by default', () => {
    const store = createTestStore()
    expect(store.getState().batchProgress).toBeNull()
  })

  it('streamingMessage is null by default', () => {
    const store = createTestStore()
    expect(store.getState().streamingMessage).toBeNull()
  })
})

describe('workbench-store batch slice', () => {
  it('activeBatchJobId is null by default', () => {
    const store = createTestStore()
    expect(store.getState().activeBatchJobId).toBeNull()
  })

  it('batchPolling is false by default', () => {
    const store = createTestStore()
    expect(store.getState().batchPolling).toBe(false)
  })

  it('postAnalysisPrompt is empty by default', () => {
    const store = createTestStore()
    expect(store.getState().postAnalysisPrompt).toBe('')
  })

  it('dismissBatchProgress clears batch state', () => {
    const store = createTestStore()
    store.getState().dismissBatchProgress()
    expect(store.getState().batchProgress).toBeNull()
    expect(store.getState().activeBatchJobId).toBeNull()
  })

  it('resetBatch clears all batch state', () => {
    const store = createTestStore()
    store.getState().resetBatch()
    expect(store.getState().activeBatchJobId).toBeNull()
    expect(store.getState().batchProgress).toBeNull()
    expect(store.getState().batchPolling).toBe(false)
    expect(store.getState().postAnalysisPrompt).toBe('')
  })

  it('cancelBatchAnalysis returns early when no active job', async () => {
    const store = createTestStore()
    // Should not throw
    await store.getState().cancelBatchAnalysis()
  })
})

describe('workbench-store streaming slice', () => {
  it('pendingApproval is null by default', () => {
    const store = createTestStore()
    expect(store.getState().pendingApproval).toBeNull()
  })

  it('reconnecting is false by default', () => {
    const store = createTestStore()
    expect(store.getState().reconnecting).toBe(false)
  })

  it('setQuotedContent updates quotedContent', () => {
    const store = createTestStore()
    store.getState().setQuotedContent('test quote')
    expect(store.getState().quotedContent).toBe('test quote')
    store.getState().setQuotedContent(null)
    expect(store.getState().quotedContent).toBeNull()
  })

  it('resetStreaming clears streaming state', () => {
    const store = createTestStore()
    store.getState().setQuotedContent('text')
    store.getState().resetStreaming()
    expect(store.getState().isStreaming).toBe(false)
    expect(store.getState().streamingMessage).toBeNull()
    // resetStreaming does NOT clear quotedContent
    expect(store.getState().quotedContent).toBe('text')
  })

  it('sendMessage is a function', () => {
    const store = createTestStore()
    expect(typeof store.getState().sendMessage).toBe('function')
  })

  it('abortStream is a function', () => {
    const store = createTestStore()
    expect(typeof store.getState().abortStream).toBe('function')
  })

  it('editAndResend is a function', () => {
    const store = createTestStore()
    expect(typeof store.getState().editAndResend).toBe('function')
  })
})

describe('workbench-store attachment slice', () => {
  it('attachments is empty by default', () => {
    const store = createTestStore()
    expect(store.getState().attachments).toEqual([])
  })

  it('addAttachment adds file to attachments', async () => {
    // Mock fetch to simulate successful upload
    const mockFetch = vi.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 'server-id-1', url: 'http://test/file.pdf' }),
    })
    vi.stubGlobal('fetch', mockFetch)
    const store = createTestStore()
    const file = new File(['test'], 'test.pdf', { type: 'application/pdf' })
    await store.getState().addAttachment(file)
    expect(store.getState().attachments).toHaveLength(1)
    expect(store.getState().attachments[0].name).toBe('test.pdf')
    vi.unstubAllGlobals()
  })

  it('removeAttachment removes file by id', () => {
    const store = createTestStore()
    // Manually set attachments with known IDs
    store.setState({
      attachments: [
        { id: 'att-1', name: 'a.pdf', type: 'application/pdf', size: 100, status: 'ready' },
        { id: 'att-2', name: 'b.pdf', type: 'application/pdf', size: 200, status: 'ready' },
      ],
    })
    expect(store.getState().attachments).toHaveLength(2)
    store.getState().removeAttachment('att-1')
    expect(store.getState().attachments).toHaveLength(1)
    expect(store.getState().attachments[0].id).toBe('att-2')
  })

  it('clearAttachments removes all attachments', () => {
    const store = createTestStore()
    store.setState({
      attachments: [
        { id: 'att-1', name: 'a.pdf', type: 'application/pdf', size: 100, status: 'ready' },
      ],
    })
    store.getState().clearAttachments()
    expect(store.getState().attachments).toEqual([])
  })
})
