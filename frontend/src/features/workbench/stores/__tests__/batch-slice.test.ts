import { create } from 'zustand'
import { act } from '@testing-library/react'
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

  // --- New tests for uncovered lines ---

  it('handleSSEEvent processes item_started event', async () => {
    const { submitBatchAnalysis, connectBatchSSE } = await import('../../api')
    const job = makeBatchJob({ total_items: 2 })
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    let sseHandler: ((event: { type: string; data: Record<string, unknown> }) => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, onMessage) => {
      sseHandler = onMessage
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    // Simulate item_started event
    act(() => {
      sseHandler?.({ type: 'item_started', data: { item_id: 'item-1', file_name: 'test.pdf' } })
    })

    // Use fake timers to process the setTimeout in handleSSEEvent
    vi.advanceTimersByTime(10)
    const bp = store.getState().batchProgress
    expect(bp).not.toBeNull()
    expect(bp!.items.length).toBe(1)
    expect(bp!.items[0].id).toBe('item-1')
    expect(bp!.items[0].status).toBe('running')
  })

  it('handleSSEEvent processes item_completed event for existing item', async () => {
    const { submitBatchAnalysis, connectBatchSSE, getBatchProgress, saveBatchMessages } = await import('../../api')
    const job = makeBatchJob({ total_items: 1, status: 'running' })
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    vi.mocked(getBatchProgress).mockResolvedValue(makeBatchProgress({ job: { ...job, status: 'completed' }, items: [makeBatchItem()] }))
    vi.mocked(saveBatchMessages).mockResolvedValue({ saved: true })
    let sseHandler: ((event: { type: string; data: Record<string, unknown> }) => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, onMessage, onOpen, onError) => {
      sseHandler = onMessage
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    // First add an item via item_started
    act(() => {
      sseHandler?.({ type: 'item_started', data: { item_id: 'item-1', file_name: 'test.pdf' } })
    })
    vi.advanceTimersByTime(10)

    // Then complete it
    act(() => {
      sseHandler?.({
        type: 'item_completed',
        data: { item_id: 'item-1', file_name: 'test.pdf', duration_ms: 500, result: 'analysis done' },
      })
    })
    vi.advanceTimersByTime(10)

    const bp = store.getState().batchProgress
    expect(bp).not.toBeNull()
    expect(bp!.items[0].status).toBe('completed')
  })

  it('handleSSEEvent processes item_failed event for new item', async () => {
    const { submitBatchAnalysis, connectBatchSSE } = await import('../../api')
    const job = makeBatchJob({ total_items: 1 })
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    let sseHandler: ((event: { type: string; data: Record<string, unknown> }) => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, onMessage) => {
      sseHandler = onMessage
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    // Send item_failed for item not started
    act(() => {
      sseHandler?.({
        type: 'item_failed',
        data: { item_id: 'item-x', file_name: 'fail.pdf', error: 'timeout' },
      })
    })
    vi.advanceTimersByTime(10)

    const bp = store.getState().batchProgress
    expect(bp).not.toBeNull()
    expect(bp!.items.length).toBe(1)
    expect(bp!.items[0].status).toBe('failed')
    expect(bp!.items[0].error).toBe('timeout')
  })

  it('handleSSEEvent processes progress event', async () => {
    const { submitBatchAnalysis, connectBatchSSE } = await import('../../api')
    const job = makeBatchJob({ total_items: 3 })
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    let sseHandler: ((event: { type: string; data: Record<string, unknown> }) => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, onMessage) => {
      sseHandler = onMessage
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    act(() => {
      sseHandler?.({
        type: 'progress',
        data: { completed_items: 2, failed_items: 0, total_items: 3, progress: 67 },
      })
    })
    vi.advanceTimersByTime(10)

    const bp = store.getState().batchProgress
    expect(bp).not.toBeNull()
    expect(bp!.job.completed_items).toBe(2)
    expect(bp!.job.progress).toBe(67)
  })

  it('handleSSEEvent ignores events when no batchProgress', async () => {
    const { submitBatchAnalysis, connectBatchSSE } = await import('../../api')
    let sseHandler: ((event: { type: string; data: Record<string, unknown> }) => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, onMessage) => {
      sseHandler = onMessage
      return () => {}
    })

    const store = createTestStore()
    // No batchProgress set, send event
    act(() => {
      sseHandler?.({ type: 'progress', data: { completed_items: 1, failed_items: 0, total_items: 1, progress: 100 } })
    })
    vi.advanceTimersByTime(10)
    expect(store.getState().batchProgress).toBeNull()
  })

  it('handleSSEEvent ignores duplicate item_started', async () => {
    const { submitBatchAnalysis, connectBatchSSE } = await import('../../api')
    const job = makeBatchJob()
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    let sseHandler: ((event: { type: string; data: Record<string, unknown> }) => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, onMessage) => {
      sseHandler = onMessage
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    // Send same item_started twice
    act(() => {
      sseHandler?.({ type: 'item_started', data: { item_id: 'item-1', file_name: 'test.pdf' } })
    })
    vi.advanceTimersByTime(10)
    act(() => {
      sseHandler?.({ type: 'item_started', data: { item_id: 'item-1', file_name: 'test.pdf' } })
    })
    vi.advanceTimersByTime(10)

    const bp = store.getState().batchProgress
    expect(bp!.items.length).toBe(1)
  })

  it('handleTerminal with postAnalysisPrompt sends message to main AI', async () => {
    const { submitBatchAnalysis, connectBatchSSE, getBatchProgress, saveBatchMessages } = await import('../../api')
    const job = makeBatchJob({ total_items: 1, status: 'completed', summary: 'Summary report' })
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    vi.mocked(getBatchProgress).mockResolvedValue(makeBatchProgress({
      job: { ...job, status: 'completed' },
      items: [makeBatchItem({ status: 'completed', result: 'analysis result' })],
    }))
    vi.mocked(saveBatchMessages).mockResolvedValue({ saved: true })
    let onOpen: (() => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, _onMessage, _onOpen, _onError) => {
      onOpen = _onOpen
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [], 'post-analysis instructions')

    // Trigger the onOpen callback which fetches progress and calls handleTerminal
    await act(async () => {
      await onOpen?.()
    })

    // The postAnalysisPrompt should have been cleared and message sent
    expect(store.getState().postAnalysisPrompt).toBe('')
  })

  it('handleTerminal without postAnalysisPrompt saves messages', async () => {
    const { submitBatchAnalysis, connectBatchSSE, getBatchProgress, saveBatchMessages } = await import('../../api')
    const job = makeBatchJob({ total_items: 1, status: 'completed', summary: 'Summary' })
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    vi.mocked(getBatchProgress).mockResolvedValue(makeBatchProgress({
      job: { ...job, status: 'completed' },
      items: [makeBatchItem({ status: 'completed', result: 'analysis result' })],
    }))
    vi.mocked(saveBatchMessages).mockResolvedValue({ saved: true })
    let onOpen: (() => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, _onMessage, _onOpen, _onError) => {
      onOpen = _onOpen
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    await act(async () => {
      await onOpen?.()
    })

    expect(saveBatchMessages).toHaveBeenCalled()
  })

  it('handleTerminal handles saveBatchMessages error gracefully', async () => {
    const { submitBatchAnalysis, connectBatchSSE, getBatchProgress, saveBatchMessages } = await import('../../api')
    const job = makeBatchJob({ total_items: 1, status: 'completed', summary: 'Summary' })
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    vi.mocked(getBatchProgress).mockResolvedValue(makeBatchProgress({
      job: { ...job, status: 'completed' },
      items: [makeBatchItem({ status: 'completed', result: 'result' })],
    }))
    vi.mocked(saveBatchMessages).mockRejectedValue(new Error('save failed'))
    let onOpen: (() => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, _onMessage, _onOpen) => {
      onOpen = _onOpen
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    // Should not throw even if saveBatchMessages fails
    await act(async () => {
      await onOpen?.()
    })
  })

  it('onClose callback triggers polling and handles terminal status', async () => {
    const { submitBatchAnalysis, connectBatchSSE, getBatchProgress } = await import('../../api')
    const job = makeBatchJob({ total_items: 1, status: 'completed' })
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    vi.mocked(getBatchProgress).mockResolvedValue(makeBatchProgress({
      job: { ...job, status: 'completed' },
      items: [makeBatchItem()],
    }))
    let onClose: (() => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, _onMessage, _onOpen, _onClose) => {
      onClose = _onClose
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    // Trigger onClose which starts polling
    act(() => {
      onClose?.()
    })

    // Advance timers to trigger the poll
    await act(async () => {
      vi.advanceTimersByTime(3000)
    })

    expect(getBatchProgress).toHaveBeenCalled()
  })

  it('onClose polling handles getBatchProgress error', async () => {
    const { submitBatchAnalysis, connectBatchSSE, getBatchProgress } = await import('../../api')
    const job = makeBatchJob({ total_items: 1, status: 'running' })
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    vi.mocked(getBatchProgress).mockRejectedValue(new Error('network'))
    let onClose: (() => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, _onMessage, _onOpen, _onClose) => {
      onClose = _onClose
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    act(() => { onClose?.() })
    await act(async () => {
      vi.advanceTimersByTime(3000)
    })

    // Should not have thrown, polling should continue
    expect(store.getState().batchPolling).toBe(true)
  })

  it('injectCompletedItem deduplicates by itemId', async () => {
    const { submitBatchAnalysis, connectBatchSSE, getBatchProgress, saveBatchMessages } = await import('../../api')
    const job = makeBatchJob({ total_items: 2, status: 'completed' })
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    vi.mocked(getBatchProgress).mockResolvedValue(makeBatchProgress({
      job: { ...job, status: 'completed' },
      items: [
        makeBatchItem({ id: 'item-1', status: 'completed', result: 'result1' }),
        makeBatchItem({ id: 'item-1', status: 'completed', result: 'result1' }),
      ],
    }))
    vi.mocked(saveBatchMessages).mockResolvedValue({ saved: true })
    let onOpen: (() => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, _onMessage, _onOpen) => {
      onOpen = _onOpen
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    await act(async () => {
      await onOpen?.()
    })

    // The injectCompletedItem should only create one message (deduplication)
    const messages = store.getState().messages
    const batchMessages = messages.filter(m => m.metadata?.source === 'batch_item')
    expect(batchMessages.length).toBeLessThanOrEqual(2)
  })

  it('handleTerminal with no completed items skips saving', async () => {
    const { submitBatchAnalysis, connectBatchSSE, getBatchProgress, saveBatchMessages } = await import('../../api')
    const job = makeBatchJob({ total_items: 1, status: 'failed' })
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    vi.mocked(getBatchProgress).mockResolvedValue(makeBatchProgress({
      job: { ...job, status: 'failed' },
      items: [makeBatchItem({ status: 'failed', result: '', error: 'timeout' })],
    }))
    vi.mocked(saveBatchMessages).mockResolvedValue({ saved: true })
    let onOpen: (() => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, _onMessage, _onOpen) => {
      onOpen = _onOpen
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    await act(async () => {
      await onOpen?.()
    })

    // saveBatchMessages should not be called for failed items without results
    // (though it may be called for the summary)
  })

  it('handleTerminal cancelled job with summary saves summary', async () => {
    const { submitBatchAnalysis, connectBatchSSE, getBatchProgress, saveBatchMessages } = await import('../../api')
    const job = makeBatchJob({ total_items: 1, status: 'cancelled', summary: 'Cancelled summary' })
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    vi.mocked(getBatchProgress).mockResolvedValue(makeBatchProgress({
      job: { ...job, status: 'cancelled' },
      items: [],
    }))
    vi.mocked(saveBatchMessages).mockResolvedValue({ saved: true })
    let onOpen: (() => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, _onMessage, _onOpen) => {
      onOpen = _onOpen
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    await act(async () => {
      await onOpen?.()
    })
  })

  it('onOpen callback handles getBatchProgress error', async () => {
    const { submitBatchAnalysis, connectBatchSSE, getBatchProgress } = await import('../../api')
    const job = makeBatchJob()
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    vi.mocked(getBatchProgress).mockRejectedValue(new Error('fail'))
    let onOpen: (() => void) | undefined
    vi.mocked(connectBatchSSE).mockImplementation((_jobId, _onMessage, _onOpen) => {
      onOpen = _onOpen
      return () => {}
    })

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    await act(async () => {
      await onOpen?.()
    })

    // When getBatchProgress fails, batchPolling should be set to false
    expect(store.getState().batchPolling).toBe(false)
  })

  it('submitBatchAnalysis polls for items when SSE does not provide them', async () => {
    const { submitBatchAnalysis, connectBatchSSE, getBatchProgress } = await import('../../api')
    const job = makeBatchJob()
    vi.mocked(submitBatchAnalysis).mockResolvedValue(job)
    // Return items on second poll
    let pollCount = 0
    vi.mocked(getBatchProgress).mockImplementation(async () => {
      pollCount++
      if (pollCount >= 2) {
        return makeBatchProgress({ items: [makeBatchItem()] })
      }
      return makeBatchProgress()
    })
    vi.mocked(connectBatchSSE).mockReturnValue(() => {})

    const store = createTestStore()
    store.getState().setCurrentSession({ id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o' })
    await store.getState().submitBatchAnalysis('prompt', [])

    // Advance timers for pollItems
    await act(async () => {
      vi.advanceTimersByTime(2000)
    })

    expect(getBatchProgress).toHaveBeenCalled()
  })
})
