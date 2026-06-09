import { create } from 'zustand'
import { createAttachmentSlice, type AttachmentSlice } from '../attachment-slice'
import type { WorkbenchStore } from '../workbench-store'

vi.mock('@/lib/token', () => ({
  getAccessToken: vi.fn(() => 'test-token'),
}))

vi.mock('@/lib/api', () => ({
  API_BASE_URL: 'http://localhost:8002/api/v1',
}))

// We need a minimal store type for testing
type TestStore = AttachmentSlice

function createTestStore() {
  return create<TestStore>()((...args) => ({
    ...createAttachmentSlice(...args as Parameters<typeof createAttachmentSlice>),
  }))
}

describe('attachment-slice', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.restoreAllMocks()
  })

  it('has correct initial state', () => {
    const store = createTestStore()
    expect(store.getState().attachments).toEqual([])
  })

  it('removeAttachment removes by id', () => {
    const store = createTestStore()
    store.setState({
      attachments: [
        { id: 'att_1', name: 'a.pdf', type: 'application/pdf', size: 100, status: 'ready' },
        { id: 'att_2', name: 'b.pdf', type: 'application/pdf', size: 200, status: 'ready' },
      ],
    })
    store.getState().removeAttachment('att_1')
    expect(store.getState().attachments).toHaveLength(1)
    expect(store.getState().attachments[0].id).toBe('att_2')
  })

  it('clearAttachments empties list', () => {
    const store = createTestStore()
    store.setState({
      attachments: [
        { id: 'att_1', name: 'a.pdf', type: 'application/pdf', size: 100, status: 'ready' },
      ],
    })
    store.getState().clearAttachments()
    expect(store.getState().attachments).toEqual([])
  })

  it('addAttachment uploads successfully', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 'server-id-1', url: 'http://test/file.pdf' }),
    } as Response)

    const store = createTestStore()
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    await store.getState().addAttachment(file)

    const attachments = store.getState().attachments
    expect(attachments).toHaveLength(1)
    expect(attachments[0].status).toBe('ready')
    expect(attachments[0].url).toBe('http://test/file.pdf')
    expect(attachments[0].name).toBe('test.pdf')
    fetchSpy.mockRestore()
  })

  it('addAttachment falls back to data URL on fetch failure', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockRejectedValue(new Error('Network error'))

    const store = createTestStore()
    const file = new File(['content'], 'test.txt', { type: 'text/plain' })
    await store.getState().addAttachment(file)

    const attachments = store.getState().attachments
    expect(attachments).toHaveLength(1)
    expect(attachments[0].status).toBe('ready')
    expect(attachments[0].url).toMatch(/^data:/)
    fetchSpy.mockRestore()
  })

  it('addAttachment handles non-ok response', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: false,
      status: 500,
      json: () => Promise.resolve({}),
    } as Response)

    const store = createTestStore()
    const file = new File(['content'], 'test.txt', { type: 'text/plain' })
    await store.getState().addAttachment(file)

    const attachments = store.getState().attachments
    expect(attachments).toHaveLength(1)
    expect(attachments[0].status).toBe('ready')
    // Falls back to data URL
    expect(attachments[0].url).toMatch(/^data:/)
    fetchSpy.mockRestore()
  })

  it('addAttachment includes Authorization header when token exists', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ id: 'server-id-1' }),
    } as Response)

    const store = createTestStore()
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })
    await store.getState().addAttachment(file)

    const [, init] = fetchSpy.mock.calls[0]
    expect((init?.headers as Record<string, string>)['Authorization']).toBe('Bearer test-token')
    fetchSpy.mockRestore()
  })

  it('addAttachment sets uploading status initially', async () => {
    let resolveFetch: (v: unknown) => void
    const fetchPromise = new Promise((resolve) => { resolveFetch = resolve })
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockReturnValue(fetchPromise as Promise<Response>)

    const store = createTestStore()
    const file = new File(['content'], 'test.pdf', { type: 'application/pdf' })

    const addPromise = store.getState().addAttachment(file)

    // Should be uploading immediately
    expect(store.getState().attachments[0].status).toBe('uploading')

    resolveFetch!({
      ok: true,
      json: () => Promise.resolve({ id: 'server-id-1' }),
    })
    await addPromise
    fetchSpy.mockRestore()
  })
})
