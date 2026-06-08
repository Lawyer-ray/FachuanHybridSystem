import { create } from 'zustand'
import { createSessionSlice } from '../session-slice'
import { createStreamingSlice } from '../streaming-slice'
import { createBatchSlice } from '../batch-slice'
import { createAttachmentSlice } from '../attachment-slice'
import type { WorkbenchStore } from '../workbench-store'

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
