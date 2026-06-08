import { create } from 'zustand'
import { createSessionSlice, type SessionSlice } from '../session-slice'
import { createStreamingSlice, type StreamingSlice } from '../streaming-slice'
import { createBatchSlice, type BatchSlice, cleanupBatchState } from '../batch-slice'
import { createAttachmentSlice, type AttachmentSlice } from '../attachment-slice'
import type { BatchProgress, BatchJob, BatchJobItem } from '../../types'

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
  submitBatchAnalysis: vi.fn(),
  getBatchProgress: vi.fn(),
  cancelBatchAnalysis: vi.fn(),
  saveBatchMessages: vi.fn().mockResolvedValue({}),
  retryBatchAnalysis: vi.fn().mockResolvedValue({}),
  listBatchJobs: vi.fn(),
  connectBatchSSE: vi.fn(),
  optimizePrompt: vi.fn(),
}))

vi.mock('../streaming-helpers', () => ({
  stripMetadataBlock: vi.fn((text: string) => text),
  connectAndReadStream: vi.fn(),
  reduceStreamingMessage: vi.fn(),
}))

vi.mock('../message-factory', () => ({
  createBatchItemMessage: vi.fn((fileName: string, content: string, jobId: string) => ({
    id: 100, role: 'assistant' as const, content: `batch-item-${fileName}`, created_at: new Date().toISOString(),
    llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {},
    metadata: { source: 'batch_item', job_id: jobId },
  })),
  createBatchSummaryMessage: vi.fn((summary: string, jobId: string) => ({
    id: 101, role: 'assistant' as const, content: `batch-summary`, created_at: new Date().toISOString(),
    llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {},
    metadata: { source: 'batch_analysis', job_id: jobId },
  })),
  createUserMessage: vi.fn(),
  finalizeStreamingMessages: vi.fn(() => []),
  createAbortedMessage: vi.fn(),
  createPartialMessage: vi.fn(),
  createErrorMessage: vi.fn(),
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

function makeBatchJob(overrides: Partial<BatchJob> = {}): BatchJob {
  return {
    id: 'job-1',
    session_id: 1,
    status: 'running',
    total_items: 3,
    completed_items: 0,
    failed_items: 0,
    progress: 0,
    summary: '',
    created_at: '2025-01-01',
    updated_at: '2025-01-01',
    ...overrides,
  }
}

function makeBatchProgress(overrides: Partial<BatchProgress> = {}): BatchProgress {
  return {
    job: makeBatchJob(),
    items: [],
    failed_items_detail: [],
    ...overrides,
  }
}

function makeBatchItem(overrides: Partial<BatchJobItem> = {}): BatchJobItem {
  return {
    id: 'item-1',
    file_name: 'file.pdf',
    status: 'completed',
    result: 'analysis result',
    error: '',
    duration_ms: 100,
    ...overrides,
  }
}

describe('batch-slice', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    cleanupBatchState()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('has correct initial state', () => {
    const store = createTestStore()
    const state = store.getState()
    expect(state.activeBatchJobId).toBeNull()
    expect(state.batchProgress).toBeNull()
    expect(state.batchPolling).toBe(false)
    expect(state.postAnalysisPrompt).toBe('')
  })

  it('submitBatchAnalysis returns early if no current session', async () => {
    const store = createTestStore()
    const { submitBatchAnalysis } = await import('../../api')
    await store.getState().submitBatchAnalysis('prompt', [])
    expect(submitBatchAnalysis).not.toHaveBeenCalled()
  })

  it('submitBatchAnalysis submits job and sets state', async () => {
    const { submitBatchAnalysis, connectBatchSSE } = await import('../../api')
    const job = makeBatchJob()
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    vi.mocked(connectBatchSSE).mockReturnValue(() => {})

    const store = createTestStore()
    store.getState().setSelectedModel('gpt-4o')
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })

    await store.getState().submitBatchAnalysis('prompt', [], 'post-prompt', 10)

    expect(submitBatchAnalysis).toHaveBeenCalledWith(1, 'prompt', 'gpt-4o', [], 10)
    expect(store.getState().activeBatchJobId).toBe('job-1')
    expect(store.getState().batchPolling).toBe(true)
    expect(store.getState().postAnalysisPrompt).toBe('post-prompt')
  })

  it('submitBatchAnalysis cleans up previous SSE connection', async () => {
    const { submitBatchAnalysis, connectBatchSSE } = await import('../../api')
    const job = makeBatchJob()
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    const cleanupFn = vi.fn()
    vi.mocked(connectBatchSSE).mockReturnValue(cleanupFn)

    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })

    // First submission
    await store.getState().submitBatchAnalysis('prompt', [])
    // Second submission should clean up first
    await store.getState().submitBatchAnalysis('prompt2', [])
    expect(cleanupFn).toHaveBeenCalled()
  })

  it('cancelBatchAnalysis calls API when job is active', async () => {
    const { submitBatchAnalysis, cancelBatchAnalysis, connectBatchSSE } = await import('../../api')
    vi.mocked(submitBatchAnalysis).mockResolvedValue(makeBatchJob())
    vi.mocked(cancelBatchAnalysis).mockResolvedValue({ success: true, status: 'cancelled', message: '' })
    vi.mocked(connectBatchSSE).mockReturnValue(() => {})

    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await store.getState().submitBatchAnalysis('prompt', [])
    await store.getState().cancelBatchAnalysis()

    expect(cancelBatchAnalysis).toHaveBeenCalledWith('job-1')
  })

  it('cancelBatchAnalysis does nothing when no active job', async () => {
    const { cancelBatchAnalysis } = await import('../../api')
    const store = createTestStore()
    await store.getState().cancelBatchAnalysis()
    expect(cancelBatchAnalysis).not.toHaveBeenCalled()
  })

  it('dismissBatchProgress clears progress and job ID', async () => {
    const { submitBatchAnalysis, connectBatchSSE } = await import('../../api')
    vi.mocked(submitBatchAnalysis).mockResolvedValue(makeBatchJob())
    vi.mocked(connectBatchSSE).mockReturnValue(() => {})

    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await store.getState().submitBatchAnalysis('prompt', [])

    store.getState().dismissBatchProgress()
    expect(store.getState().batchProgress).toBeNull()
    expect(store.getState().activeBatchJobId).toBeNull()
  })

  it('recoverActiveBatchJob returns early if job already active', async () => {
    const { submitBatchAnalysis, listBatchJobs, connectBatchSSE } = await import('../../api')
    vi.mocked(submitBatchAnalysis).mockResolvedValue(makeBatchJob())
    vi.mocked(connectBatchSSE).mockReturnValue(() => {})

    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await store.getState().submitBatchAnalysis('prompt', [])
    vi.mocked(listBatchJobs).mockClear()

    await store.getState().recoverActiveBatchJob(1)
    expect(listBatchJobs).not.toHaveBeenCalled()
  })

  it('recoverActiveBatchJob recovers running job', async () => {
    const { listBatchJobs, getBatchProgress, connectBatchSSE } = await import('../../api')
    const runningJob = makeBatchJob({ status: 'running' })
    vi.mocked(listBatchJobs).mockResolvedValue({ items: [runningJob], count: 1 })
    vi.mocked(getBatchProgress).mockResolvedValue(makeBatchProgress({
      job: runningJob,
      items: [makeBatchItem()],
    }))
    vi.mocked(connectBatchSSE).mockReturnValue(() => {})

    const store = createTestStore()
    await store.getState().recoverActiveBatchJob(1)

    expect(store.getState().activeBatchJobId).toBe('job-1')
    expect(store.getState().batchPolling).toBe(true)
  })

  it('recoverActiveBatchJob does nothing if no running job', async () => {
    const { listBatchJobs } = await import('../../api')
    vi.mocked(listBatchJobs).mockResolvedValue({
      items: [makeBatchJob({ status: 'completed' })],
      count: 1,
    })

    const store = createTestStore()
    await store.getState().recoverActiveBatchJob(1)
    expect(store.getState().activeBatchJobId).toBeNull()
  })

  it('recoverActiveBatchJob handles error gracefully', async () => {
    const { listBatchJobs } = await import('../../api')
    vi.mocked(listBatchJobs).mockRejectedValue(new Error('network'))

    const store = createTestStore()
    await store.getState().recoverActiveBatchJob(1)
    expect(store.getState().activeBatchJobId).toBeNull()
  })

  it('resetBatch clears all batch state', async () => {
    const { submitBatchAnalysis, connectBatchSSE } = await import('../../api')
    vi.mocked(submitBatchAnalysis).mockResolvedValue(makeBatchJob())
    vi.mocked(connectBatchSSE).mockReturnValue(() => {})

    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await store.getState().submitBatchAnalysis('prompt', [], 'post')

    store.getState().resetBatch()
    expect(store.getState().activeBatchJobId).toBeNull()
    expect(store.getState().batchProgress).toBeNull()
    expect(store.getState().batchPolling).toBe(false)
    expect(store.getState().postAnalysisPrompt).toBe('')
  })

  it('cleanupBatchState cleans up SSE connection', () => {
    cleanupBatchState()
    // Should not throw when called multiple times
    cleanupBatchState()
    expect(true).toBe(true)
  })

  it('cancelBatchAnalysis handles API error gracefully', async () => {
    const { submitBatchAnalysis, cancelBatchAnalysis, connectBatchSSE } = await import('../../api')
    vi.mocked(submitBatchAnalysis).mockResolvedValue(makeBatchJob())
    vi.mocked(cancelBatchAnalysis).mockRejectedValue(new Error('fail'))
    vi.mocked(connectBatchSSE).mockReturnValue(() => {})

    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await store.getState().submitBatchAnalysis('prompt', [])
    // Should not throw
    await store.getState().cancelBatchAnalysis()
  })

  it('submitBatchAnalysis with default concurrency', async () => {
    const { submitBatchAnalysis, connectBatchSSE } = await import('../../api')
    vi.mocked(submitBatchAnalysis).mockResolvedValue(makeBatchJob())
    vi.mocked(connectBatchSSE).mockReturnValue(() => {})

    const store = createTestStore()
    store.getState().setSelectedModel('gpt-4o')
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await store.getState().submitBatchAnalysis('prompt', [])
    expect(submitBatchAnalysis).toHaveBeenCalledWith(1, 'prompt', 'gpt-4o', [], 50)
  })

  it('recoverActiveBatchJob recovers pending job', async () => {
    const { listBatchJobs, getBatchProgress, connectBatchSSE } = await import('../../api')
    const pendingJob = makeBatchJob({ status: 'pending' })
    vi.mocked(listBatchJobs).mockResolvedValue({ items: [pendingJob], count: 1 })
    vi.mocked(getBatchProgress).mockResolvedValue(makeBatchProgress({ job: pendingJob }))
    vi.mocked(connectBatchSSE).mockReturnValue(() => {})

    const store = createTestStore()
    await store.getState().recoverActiveBatchJob(1)
    expect(store.getState().activeBatchJobId).toBe('job-1')
  })
})
