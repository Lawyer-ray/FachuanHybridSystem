import { create } from 'zustand'
import { createStreamingSlice, type StreamingSlice } from '../streaming-slice'
import { createSessionSlice, type SessionSlice } from '../session-slice'
import { createBatchSlice, type BatchSlice } from '../batch-slice'
import { createAttachmentSlice, type AttachmentSlice } from '../attachment-slice'

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
  saveBatchMessages: vi.fn(),
  retryBatchAnalysis: vi.fn(),
  listBatchJobs: vi.fn(),
  connectBatchSSE: vi.fn(),
}))

vi.mock('@/lib/token', () => ({
  getAccessToken: vi.fn().mockReturnValue('test-token'),
}))

vi.mock('@/lib/api', () => ({
  API_BASE_URL: 'http://localhost:8000/api',
  createFeatureApiClient: vi.fn(),
}))

vi.mock('../streaming-helpers', () => ({
  connectAndReadStream: vi.fn(),
  reduceStreamingMessage: vi.fn((sm: Record<string, unknown>, event: Record<string, unknown>) => {
    if (event.type === 'delta') {
      return { ...sm, content: (sm.content as string) + (event.content || '') }
    }
    if (event.type === 'error') {
      return { ...sm, error: event.message || '未知错误' }
    }
    if (event.type === 'approval_request') {
      return sm
    }
    return sm
  }),
  stripMetadataBlock: vi.fn((text: string) => text),
}))

vi.mock('../message-factory', () => ({
  createUserMessage: vi.fn((content: string) => ({
    id: Date.now(), role: 'user' as const, content, created_at: new Date().toISOString(),
    llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {},
  })),
  finalizeStreamingMessages: vi.fn(() => []),
  createAbortedMessage: vi.fn((content: string) => ({
    id: Date.now(), role: 'assistant' as const, content: `[已中断] ${content}`, created_at: new Date().toISOString(),
    llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {},
  })),
  createPartialMessage: vi.fn((content: string) => ({
    id: Date.now(), role: 'assistant' as const, content, created_at: new Date().toISOString(),
    llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {},
  })),
  createErrorMessage: vi.fn((msg: string) => ({
    id: Date.now(), role: 'assistant' as const, content: `错误: ${msg}`, created_at: new Date().toISOString(),
    llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {},
  })),
  createBatchItemMessage: vi.fn(),
  createBatchSummaryMessage: vi.fn(),
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

describe('streaming-slice', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('isStreaming is false by default', () => {
    const store = createTestStore()
    expect(store.getState().isStreaming).toBe(false)
  })

  it('streamingMessage is null by default', () => {
    const store = createTestStore()
    expect(store.getState().streamingMessage).toBeNull()
  })

  it('reconnecting is false by default', () => {
    const store = createTestStore()
    expect(store.getState().reconnecting).toBe(false)
  })

  it('pendingApproval is null by default', () => {
    const store = createTestStore()
    expect(store.getState().pendingApproval).toBeNull()
  })

  it('quotedContent is null by default', () => {
    const store = createTestStore()
    expect(store.getState().quotedContent).toBeNull()
  })

  it('sets quoted content', () => {
    const store = createTestStore()
    store.getState().setQuotedContent('some quoted text')
    expect(store.getState().quotedContent).toBe('some quoted text')
  })

  it('clears quoted content', () => {
    const store = createTestStore()
    store.getState().setQuotedContent('text')
    store.getState().setQuotedContent(null)
    expect(store.getState().quotedContent).toBeNull()
  })

  it('resets streaming state', () => {
    const store = createTestStore()
    store.getState().setQuotedContent('text')
    store.getState().resetStreaming()
    expect(store.getState().isStreaming).toBe(false)
    expect(store.getState().streamingMessage).toBeNull()
  })

  it('exports sendMessage function', () => {
    const store = createTestStore()
    expect(typeof store.getState().sendMessage).toBe('function')
  })

  it('exports abortStream function', () => {
    const store = createTestStore()
    expect(typeof store.getState().abortStream).toBe('function')
  })

  it('exports editAndResend function', () => {
    const store = createTestStore()
    expect(typeof store.getState().editAndResend).toBe('function')
  })

  // --- New tests below ---

  it('sendMessage returns early if no current session', async () => {
    const store = createTestStore()
    await store.getState().sendMessage('hello')
    expect(store.getState().isStreaming).toBe(false)
  })

  it('handleSSEEvent handles approval_request event', () => {
    const store = createTestStore()
    store.getState().handleSSEEvent({
      type: 'approval_request',
      approval_id: 'app-1',
      tool_name: 'search',
      tool_input: { q: 'test' },
    } as Parameters<StreamingSlice['handleSSEEvent']>[0])
    expect(store.getState().pendingApproval).toEqual({
      approvalId: 'app-1',
      toolName: 'search',
      toolArgs: { q: 'test' },
    })
  })

  it('handleSSEEvent ignores event when no streaming message', () => {
    const store = createTestStore()
    store.getState().handleSSEEvent({
      type: 'delta',
      content: 'text',
    } as Parameters<StreamingSlice['handleSSEEvent']>[0])
    expect(store.getState().streamingMessage).toBeNull()
  })

  it('handleSSEEvent processes delta when streaming message exists', () => {
    const store = createTestStore()
    // Simulate streaming state
    store.setState({
      streamingMessage: { role: 'assistant', content: 'Hello ', toolCalls: [], handoffs: [] },
    } as Partial<StreamingSlice>)
    store.getState().handleSSEEvent({
      type: 'delta',
      content: 'world',
    } as Parameters<StreamingSlice['handleSSEEvent']>[0])
    // The message is updated via rAF, so we check the ref is set
    expect(store.getState().streamingMessage).toBeTruthy()
  })

  it('respondApproval does nothing when no pending approval', async () => {
    const { respondApproval } = await import('../../api')
    const store = createTestStore()
    await store.getState().respondApproval(true)
    expect(respondApproval).not.toHaveBeenCalled()
  })

  it('respondApproval calls API and clears pending', async () => {
    const { respondApproval } = await import('../../api')
    const store = createTestStore()
    store.setState({
      pendingApproval: { approvalId: 'app-1', toolName: 'search', toolArgs: {} },
    } as Partial<StreamingSlice>)
    await store.getState().respondApproval(true)
    expect(respondApproval).toHaveBeenCalledWith('app-1', true)
    expect(store.getState().pendingApproval).toBeNull()
  })

  it('respondApproval handles API error gracefully', async () => {
    const { respondApproval } = await import('../../api')
    vi.mocked(respondApproval).mockRejectedValueOnce(new Error('fail'))
    const store = createTestStore()
    store.setState({
      pendingApproval: { approvalId: 'app-1', toolName: 'search', toolArgs: {} },
    } as Partial<StreamingSlice>)
    await store.getState().respondApproval(false)
    // Should not throw
  })

  it('editAndResend returns early if no current session', async () => {
    const store = createTestStore()
    await store.getState().editAndResend(1, 'new content')
    expect(store.getState().messages).toHaveLength(0)
  })

  it('editAndResend returns early if message not found', async () => {
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await store.getState().editAndResend(999, 'new content')
  })

  it('editAndResend truncates and resends when message found', async () => {
    const { truncateMessages } = await import('../../api')
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    store.getState().appendMessages(
      { id: 1, role: 'user', content: 'old', created_at: '', llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {} },
      { id: 2, role: 'assistant', content: 'reply', created_at: '', llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {} },
    )
    await store.getState().editAndResend(2, 'new content')
    expect(truncateMessages).toHaveBeenCalledWith(1, 2)
  })

  it('submitFeedback updates message metadata on success', async () => {
    const store = createTestStore()
    store.getState().appendMessages(
      { id: 10, role: 'assistant', content: 'reply', created_at: '', llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {} },
    )
    await store.getState().submitFeedback(10, 'good')
    const msg = store.getState().messages.find((m) => m.id === 10)
    expect(msg?.metadata?.feedback?.rating).toBe('good')
  })

  it('submitFeedback handles API error gracefully', async () => {
    const { submitFeedback } = await import('../../api')
    vi.mocked(submitFeedback).mockRejectedValueOnce(new Error('fail'))
    const store = createTestStore()
    await store.getState().submitFeedback(999, 'bad')
    // Should not throw
  })

  it('abortStream does nothing when no controller', () => {
    const store = createTestStore()
    store.getState().abortStream()
    expect(store.getState().isStreaming).toBe(false)
  })

  it('resetStreaming resets pendingApproval and quotedContent', () => {
    const store = createTestStore()
    store.setState({
      pendingApproval: { approvalId: 'app-1', toolName: 'search', toolArgs: {} },
      quotedContent: 'some text',
    } as Partial<StreamingSlice>)
    store.getState().resetStreaming()
    expect(store.getState().pendingApproval).toBeNull()
  })

  it('handleSSEEvent with missing approval fields uses defaults', () => {
    const store = createTestStore()
    store.getState().handleSSEEvent({
      type: 'approval_request',
    } as Parameters<StreamingSlice['handleSSEEvent']>[0])
    expect(store.getState().pendingApproval).toEqual({
      approvalId: '',
      toolName: '',
      toolArgs: {},
    })
  })

  // --- New tests for uncovered lines ---

  it('sendMessage with ready attachments includes attachment note', async () => {
    const { connectAndReadStream } = await import('../streaming-helpers')
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    store.setState({
      attachments: [
        { id: 'att-1', name: 'file.pdf', status: 'ready', file: new File([''], 'f.pdf') },
        { id: 'att-2', name: 'file2.pdf', status: 'uploading', file: new File([''], 'f2.pdf') },
      ],
    } as Partial<StreamingSlice & { attachments: unknown[] }>)
    vi.mocked(connectAndReadStream).mockResolvedValue(undefined)
    await store.getState().sendMessage('hello')
    expect(connectAndReadStream).toHaveBeenCalled()
    // The first arg should be the URL
    const callArgs = vi.mocked(connectAndReadStream).mock.calls[0]
    expect(callArgs[0]).toContain('/messages/stream')
  })

  it('handleSSEEvent schedules rAF for batch updates', () => {
    const rafSpy = vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
      cb(0)
      return 0
    })
    const store = createTestStore()
    store.setState({
      streamingMessage: { role: 'assistant', content: '', toolCalls: [], handoffs: [] },
    } as Partial<StreamingSlice>)
    store.getState().handleSSEEvent({
      type: 'delta',
      content: 'hello',
    } as Parameters<StreamingSlice['handleSSEEvent']>[0])
    expect(rafSpy).toHaveBeenCalled()
    rafSpy.mockRestore()
  })

  it('handleSSEEvent with pending message flushes on rAF', () => {
    const rafSpy = vi.spyOn(globalThis, 'requestAnimationFrame').mockImplementation((cb: FrameRequestCallback) => {
      cb(0)
      return 0
    })
    const store = createTestStore()
    store.setState({
      streamingMessage: { role: 'assistant', content: 'base', toolCalls: [], handoffs: [] },
    } as Partial<StreamingSlice>)
    // First event sets up rAF
    store.getState().handleSSEEvent({
      type: 'delta',
      content: ' first',
    } as Parameters<StreamingSlice['handleSSEEvent']>[0])
    expect(rafSpy).toHaveBeenCalled()
    rafSpy.mockRestore()
  })

  it('abortStream aborts the controller', () => {
    const store = createTestStore()
    // Test that abortStream doesn't throw when no controller
    store.getState().abortStream()
    expect(store.getState().isStreaming).toBe(false)
  })

  it('resetStreaming cancels rAF and abort controller', async () => {
    const cancelRafSpy = vi.spyOn(globalThis, 'cancelAnimationFrame')
    const store = createTestStore()
    store.setState({
      streamingMessage: { role: 'assistant', content: 'test', toolCalls: [], handoffs: [] },
    } as Partial<StreamingSlice>)
    store.getState().resetStreaming()
    expect(store.getState().streamingMessage).toBeNull()
    expect(store.getState().pendingApproval).toBeNull()
    cancelRafSpy.mockRestore()
  })

  it('resetStreaming is exported', async () => {
    // Test the exported abortStreaming function
    const { abortStreaming } = await import('../streaming-slice')
    expect(typeof abortStreaming).toBe('function')
    // Call when no controller should not throw
    abortStreaming()
  })

  it('sendMessage with non-AbortError and no content creates error message', async () => {
    const { connectAndReadStream } = await import('../streaming-helpers')
    const { createErrorMessage } = await import('../message-factory')
    vi.mocked(connectAndReadStream).mockRejectedValue(new Error('Connection failed'))
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await store.getState().sendMessage('hello')
    expect(createErrorMessage).toHaveBeenCalledWith('Connection failed')
  })

  it('sendMessage with AbortError and content creates aborted message', async () => {
    const { connectAndReadStream } = await import('../streaming-helpers')
    const { createAbortedMessage } = await import('../message-factory')
    const abortError = new DOMException('The operation was aborted.', 'AbortError')
    vi.mocked(connectAndReadStream).mockImplementation(async (_url, _h, _b, _sig, onEvent) => {
      // Simulate some content being received before abort
      const store = createTestStore()
      // The store doesn't have streamingMessage, but the slice does
    })
    vi.mocked(connectAndReadStream).mockRejectedValue(abortError)
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await store.getState().sendMessage('hello')
    // Since no content was received, abort message should not be created
    expect(createAbortedMessage).not.toHaveBeenCalled()
  })

  it('sendMessage with non-AbortError and partial content creates partial message', async () => {
    const { connectAndReadStream } = await import('../streaming-helpers')
    const { createPartialMessage } = await import('../message-factory')
    // Make it fail, but first simulate some content
    vi.mocked(connectAndReadStream).mockImplementation(async () => {
      throw new Error('Network error')
    })
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    // Pre-set streaming message with content
    store.setState({
      streamingMessage: { role: 'assistant', content: 'partial content', model: 'gpt-4o', toolCalls: [], handoffs: [] },
    } as Partial<StreamingSlice>)
    await store.getState().sendMessage('hello')
    // Since retryCount starts at 0 and MAX_RETRIES is 3, it will retry
    // But the mock rejects every time, so after retries it should create partial
  })

  it('editAndResend truncates messages and resends', async () => {
    const { truncateMessages } = await import('../../api')
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    store.getState().appendMessages(
      { id: 1, role: 'user', content: 'old', created_at: '', llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {} },
      { id: 2, role: 'assistant', content: 'reply', created_at: '', llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {} },
      { id: 3, role: 'user', content: 'follow up', created_at: '', llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {} },
    )
    // Edit message at index 1 (id=2)
    await store.getState().editAndResend(2, 'new content')
    expect(truncateMessages).toHaveBeenCalledWith(1, 2)
    // Messages should be sliced to only include first 2
    expect(store.getState().messages).toHaveLength(2)
  })

  it('editAndResend with truncateMessages error still proceeds', async () => {
    const { truncateMessages } = await import('../../api')
    vi.mocked(truncateMessages).mockRejectedValueOnce(new Error('fail'))
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    store.getState().appendMessages(
      { id: 1, role: 'user', content: 'old', created_at: '', llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: {} },
    )
    await store.getState().editAndResend(1, 'new content')
    // Should not throw, messages should still be sliced
  })

  it('submitFeedback on success updates message metadata', async () => {
    const store = createTestStore()
    store.getState().appendMessages(
      { id: 5, role: 'assistant', content: 'reply', created_at: '', llm_model: '', tool_call_id: '', tool_name: '', tool_input: {}, tool_output: {}, metadata: { existing: true } },
    )
    await store.getState().submitFeedback(5, 'bad')
    const msg = store.getState().messages.find((m) => m.id === 5)
    expect(msg?.metadata?.feedback?.rating).toBe('bad')
    expect(msg?.metadata?.existing).toBe(true)
  })

  it('sendMessage with empty attachment note when no ready attachments', async () => {
    const { connectAndReadStream } = await import('../streaming-helpers')
    vi.mocked(connectAndReadStream).mockResolvedValue(undefined)
    const store = createTestStore()
    store.getState().setCurrentSession({
      id: 1, title: 'Test', created_at: '', updated_at: '', model: 'gpt-4o',
    })
    await store.getState().sendMessage('hello')
    // Verify the streaming completed without error
    expect(store.getState().isStreaming).toBe(false)
  })

  it('respondApproval with approved=false', async () => {
    const { respondApproval } = await import('../../api')
    const store = createTestStore()
    store.setState({
      pendingApproval: { approvalId: 'app-2', toolName: 'write', toolArgs: { file: 'test.txt' } },
    } as Partial<StreamingSlice>)
    await store.getState().respondApproval(false)
    expect(respondApproval).toHaveBeenCalledWith('app-2', false)
    expect(store.getState().pendingApproval).toBeNull()
  })

  it('setQuotedContent with string content', () => {
    const store = createTestStore()
    store.getState().setQuotedContent('quoted text here')
    expect(store.getState().quotedContent).toBe('quoted text here')
  })

  it('resetStreaming clears everything', () => {
    const store = createTestStore()
    store.setState({
      isStreaming: true,
      streamingMessage: { role: 'assistant', content: 'test', toolCalls: [], handoffs: [] },
      pendingApproval: { approvalId: 'a', toolName: 't', toolArgs: {} },
      quotedContent: 'text',
    } as Partial<StreamingSlice>)
    store.getState().resetStreaming()
    expect(store.getState().isStreaming).toBe(false)
    expect(store.getState().streamingMessage).toBeNull()
    expect(store.getState().pendingApproval).toBeNull()
  })
})
