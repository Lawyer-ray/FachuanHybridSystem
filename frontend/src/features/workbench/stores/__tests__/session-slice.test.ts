import { create } from 'zustand'
import { createSessionSlice, type SessionSlice } from '../session-slice'
import { createStreamingSlice, type StreamingSlice } from '../streaming-slice'
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
})
