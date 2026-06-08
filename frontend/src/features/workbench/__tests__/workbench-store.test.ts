// Mock the slice creators first, before importing
vi.mock('../stores/session-slice', () => ({
  createSessionSlice: () => ({
    sessions: [],
    currentSessionId: null,
    createSession: vi.fn(),
    deleteSession: vi.fn(),
    setCurrentSession: vi.fn(),
    addMessage: vi.fn(),
    updateMessage: vi.fn(),
    clearMessages: vi.fn(),
  }),
}))

vi.mock('../stores/streaming-slice', () => ({
  createStreamingSlice: () => ({
    isStreaming: false,
    streamingContent: '',
    startStreaming: vi.fn(),
    stopStreaming: vi.fn(),
    appendContent: vi.fn(),
    resetStreaming: vi.fn(),
  }),
}))

vi.mock('../stores/batch-slice', () => ({
  createBatchSlice: () => ({
    batchItems: [],
    isBatchProcessing: false,
    addBatchItem: vi.fn(),
    removeBatchItem: vi.fn(),
    clearBatch: vi.fn(),
    startBatch: vi.fn(),
  }),
}))

vi.mock('../stores/attachment-slice', () => ({
  createAttachmentSlice: () => ({
    attachments: [],
    uploadProgress: {},
    addAttachment: vi.fn(),
    removeAttachment: vi.fn(),
    clearAttachments: vi.fn(),
  }),
}))

import { useWorkbenchStore } from '../stores/workbench-store'

describe('workbench-store', () => {
  it('exports useWorkbenchStore hook', () => {
    expect(useWorkbenchStore).toBeDefined()
    expect(typeof useWorkbenchStore).toBe('function')
  })

  it('returns store with session slice properties', () => {
    const state = useWorkbenchStore.getState()
    expect(state).toHaveProperty('sessions')
    expect(state).toHaveProperty('currentSessionId')
    expect(state).toHaveProperty('createSession')
  })

  it('returns store with streaming slice properties', () => {
    const state = useWorkbenchStore.getState()
    expect(state).toHaveProperty('isStreaming')
    expect(state).toHaveProperty('streamingContent')
    expect(state).toHaveProperty('startStreaming')
  })

  it('returns store with batch slice properties', () => {
    const state = useWorkbenchStore.getState()
    expect(state).toHaveProperty('batchItems')
    expect(state).toHaveProperty('isBatchProcessing')
    expect(state).toHaveProperty('addBatchItem')
  })

  it('returns store with attachment slice properties', () => {
    const state = useWorkbenchStore.getState()
    expect(state).toHaveProperty('attachments')
    expect(state).toHaveProperty('addAttachment')
    expect(state).toHaveProperty('removeAttachment')
  })
})
