import { create } from 'zustand'
import { createStreamingSlice, type StreamingSlice } from '../streaming-slice'
import { createSessionSlice, type SessionSlice } from '../session-slice'
import { createBatchSlice, type BatchSlice } from '../batch-slice'
import { createAttachmentSlice, type AttachmentSlice } from '../attachment-slice'

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
})
