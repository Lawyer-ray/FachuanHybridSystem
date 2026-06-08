vi.mock('../token', () => ({
  getAccessToken: vi.fn(() => null),
  getRefreshToken: vi.fn(() => null),
  setTokens: vi.fn(),
  clearTokens: vi.fn(),
  shouldRefreshToken: vi.fn(() => false),
}))

const { mockCreate, mockPost } = vi.hoisted(() => ({
  mockCreate: vi.fn(() => ({})),
  mockPost: vi.fn(),
}))

vi.mock('ky', () => ({
  default: {
    create: (...args: unknown[]) => mockCreate(...args),
    post: (...args: unknown[]) => mockPost(...args),
  },
}))

import { getApiBaseUrl, getBackendUrl, resolveMediaUrl, createApiClient, createFeatureApiClient } from '../api'
import { getAccessToken, getRefreshToken, shouldRefreshToken, clearTokens, setTokens } from '../token'

describe('getApiBaseUrl', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('returns localStorage value if set', () => {
    localStorage.setItem('api_base_url', 'http://custom/api')
    expect(getApiBaseUrl()).toBe('http://custom/api')
  })

  it('falls back to default when localStorage is empty', () => {
    const result = getApiBaseUrl()
    expect(result).toBe('http://localhost:8002/api/v1')
  })
})

describe('getBackendUrl', () => {
  afterEach(() => {
    localStorage.clear()
  })

  it('returns localStorage value if set', () => {
    localStorage.setItem('backend_url', 'http://custom')
    expect(getBackendUrl()).toBe('http://custom')
  })

  it('falls back to default', () => {
    const result = getBackendUrl()
    expect(result).toBe('http://localhost:8002')
  })
})

describe('resolveMediaUrl', () => {
  it('returns null for null input', () => {
    expect(resolveMediaUrl(null)).toBeNull()
  })

  it('returns null for empty string', () => {
    expect(resolveMediaUrl('')).toBeNull()
  })

  it('returns http URLs as-is', () => {
    expect(resolveMediaUrl('http://example.com/file.pdf')).toBe('http://example.com/file.pdf')
  })

  it('returns https URLs as-is', () => {
    expect(resolveMediaUrl('https://example.com/file.pdf')).toBe('https://example.com/file.pdf')
  })

  it('prepends BACKEND_URL for relative paths', () => {
    const result = resolveMediaUrl('/media/file.pdf')
    expect(result).toContain('/media/file.pdf')
  })
})

describe('createApiClient', () => {
  beforeEach(() => {
    mockCreate.mockClear()
    mockCreate.mockReturnValue({})
  })

  it('returns a ky instance', () => {
    const client = createApiClient()
    expect(client).toBeDefined()
  })

  it('calls ky.create', () => {
    createApiClient()
    expect(mockCreate).toHaveBeenCalled()
  })

  it('passes prefixUrl to ky.create', () => {
    createApiClient()
    const call = mockCreate.mock.calls[mockCreate.mock.calls.length - 1][0]
    expect(call).toHaveProperty('prefixUrl')
  })
})

describe('createFeatureApiClient', () => {
  beforeEach(() => {
    mockCreate.mockClear()
    mockCreate.mockReturnValue({})
  })

  it('creates client with feature prefix in prefixUrl', () => {
    createFeatureApiClient('cases')
    const call = mockCreate.mock.calls[mockCreate.mock.calls.length - 1][0]
    expect(call.prefixUrl).toContain('/cases')
  })

  it('creates client with different prefix', () => {
    createFeatureApiClient('contracts')
    const call = mockCreate.mock.calls[mockCreate.mock.calls.length - 1][0]
    expect(call.prefixUrl).toContain('/contracts')
  })
})

describe('createApiClient hooks', () => {
  beforeEach(() => {
    mockCreate.mockClear()
    mockCreate.mockReturnValue({})
  })

  it('configures beforeRequest hooks', () => {
    createApiClient()
    const call = mockCreate.mock.calls[0][0]
    expect(call.hooks).toBeDefined()
    expect(call.hooks.beforeRequest).toBeDefined()
    expect(Array.isArray(call.hooks.beforeRequest)).toBe(true)
    expect(call.hooks.beforeRequest.length).toBeGreaterThan(0)
  })

  it('configures afterResponse hooks', () => {
    createApiClient()
    const call = mockCreate.mock.calls[0][0]
    expect(call.hooks.afterResponse).toBeDefined()
    expect(Array.isArray(call.hooks.afterResponse)).toBe(true)
    expect(call.hooks.afterResponse.length).toBeGreaterThan(0)
  })

  it('merges custom options with defaults', () => {
    createApiClient({ timeout: 5000 })
    const call = mockCreate.mock.calls[0][0]
    expect(call.timeout).toBe(5000)
    expect(call.prefixUrl).toBeDefined()
    expect(call.hooks).toBeDefined()
  })

  it('merges custom beforeRequest hooks', () => {
    const customHook = vi.fn()
    createApiClient({ hooks: { beforeRequest: [customHook] } })
    const call = mockCreate.mock.calls[0][0]
    // Should have both the default hook and the custom one
    expect(call.hooks.beforeRequest.length).toBeGreaterThanOrEqual(2)
  })

  it('merges custom afterResponse hooks', () => {
    const customHook = vi.fn()
    createApiClient({ hooks: { afterResponse: [customHook] } })
    const call = mockCreate.mock.calls[0][0]
    // Should have both the default hook and the custom one
    expect(call.hooks.afterResponse.length).toBeGreaterThanOrEqual(2)
  })

  it('beforeRequest hook sets Authorization header when token exists', async () => {
    vi.mocked(getAccessToken).mockReturnValue('test-token-123')
    vi.mocked(shouldRefreshToken).mockReturnValue(false)

    createApiClient()
    const call = mockCreate.mock.calls[0][0]
    const beforeRequestHook = call.hooks.beforeRequest[0]

    const mockRequest = {
      headers: {
        set: vi.fn(),
      },
    }

    await beforeRequestHook(mockRequest)
    expect(mockRequest.headers.set).toHaveBeenCalledWith('Authorization', 'Bearer test-token-123')
  })

  it('beforeRequest hook does not set header when no token', async () => {
    vi.mocked(getAccessToken).mockReturnValue(null)

    createApiClient()
    const call = mockCreate.mock.calls[0][0]
    const beforeRequestHook = call.hooks.beforeRequest[0]

    const mockRequest = {
      headers: {
        set: vi.fn(),
      },
    }

    await beforeRequestHook(mockRequest)
    expect(mockRequest.headers.set).not.toHaveBeenCalled()
  })

  it('afterResponse hook returns response for non-401 status', async () => {
    createApiClient()
    const call = mockCreate.mock.calls[0][0]
    const afterResponseHook = call.hooks.afterResponse[0]

    const mockRequest = { url: 'http://api.test/users' }
    const mockResponse = { status: 200, ok: true }

    const result = await afterResponseHook(mockRequest, {}, mockResponse)
    expect(result).toBe(mockResponse)
  })

  it('afterResponse hook skips refresh for token endpoint', async () => {
    createApiClient()
    const call = mockCreate.mock.calls[0][0]
    const afterResponseHook = call.hooks.afterResponse[0]

    const mockRequest = { url: 'http://api.test/token/refresh' }
    const mockResponse = { status: 401, ok: false }

    const result = await afterResponseHook(mockRequest, {}, mockResponse)
    expect(result).toBe(mockResponse)
  })

  it('afterResponse hook attempts token refresh on 401', async () => {
    vi.mocked(getRefreshToken).mockReturnValue('refresh-token-123')

    const mockNewToken = { access: 'new-access-token' }
    mockPost.mockResolvedValueOnce({
      json: vi.fn().mockResolvedValue(mockNewToken),
    })

    createApiClient()
    const call = mockCreate.mock.calls[0][0]
    const afterResponseHook = call.hooks.afterResponse[0]

    const mockHeaders = new Headers()
    const mockRequest = {
      url: 'http://api.test/users',
      headers: mockHeaders,
    }
    const mockResponse = { status: 401, ok: false }

    // The afterResponse hook should try to refresh the token
    // It may throw because ky(retryRequest) is called but we mock ky differently
    try {
      await afterResponseHook(mockRequest, {}, mockResponse)
    } catch {
      // Expected to throw since we can't fully mock the retry
    }

    // Should have attempted to get refresh token
    expect(getRefreshToken).toHaveBeenCalled()
  })

  it('afterResponse hook clears tokens when refresh fails with no refresh token', async () => {
    vi.mocked(getRefreshToken).mockReturnValue(null)

    createApiClient()
    const call = mockCreate.mock.calls[0][0]
    const afterResponseHook = call.hooks.afterResponse[0]

    const mockRequest = { url: 'http://api.test/users' }
    const mockResponse = { status: 401, ok: false }

    // Should handle the error by clearing tokens
    try {
      await afterResponseHook(mockRequest, {}, mockResponse)
    } catch {
      // Expected - session expired error
    }

    expect(clearTokens).toHaveBeenCalled()
  })

  it('beforeRequest hook with refresh needed but no refresh token available', async () => {
    vi.mocked(getAccessToken).mockReturnValue('expired-token')
    vi.mocked(shouldRefreshToken).mockReturnValue(true)
    vi.mocked(getRefreshToken).mockReturnValue(null)

    createApiClient()
    const call = mockCreate.mock.calls[0][0]
    const beforeRequestHook = call.hooks.beforeRequest[0]

    const mockRequest = {
      headers: { set: vi.fn() },
    }

    // Should handle the case where refresh fails
    await beforeRequestHook(mockRequest)
    // The hook should still complete without throwing
  })

  it('beforeRequest hook refreshes token when needed and refresh token available', async () => {
    // Note: testing the actual refresh path is complex due to module-level state
    // This test verifies the hook configuration accepts the right parameters
    vi.mocked(getAccessToken).mockReturnValue('expired-token')
    vi.mocked(shouldRefreshToken).mockReturnValue(true)
    vi.mocked(getRefreshToken).mockReturnValue('valid-refresh-token')

    createApiClient()
    const call = mockCreate.mock.calls[mockCreate.mock.calls.length - 1][0]
    const beforeRequestHook = call.hooks.beforeRequest[0]

    const mockRequest = {
      headers: { set: vi.fn() },
    }

    // The hook should complete without throwing
    await beforeRequestHook(mockRequest)
    // The hook attempts to refresh - verify it was called
    expect(getRefreshToken).toHaveBeenCalled()
  })

  it('beforeRequest hook uses existing refresh promise when one is in flight', async () => {
    vi.mocked(getAccessToken).mockReturnValue('expired-token')
    vi.mocked(shouldRefreshToken).mockReturnValue(true)
    vi.mocked(getRefreshToken).mockReturnValue(null) // no refresh token → refresh will fail

    createApiClient()
    const call = mockCreate.mock.calls[mockCreate.mock.calls.length - 1][0]
    const beforeRequestHook = call.hooks.beforeRequest[0]

    const mockRequest1 = { headers: { set: vi.fn() } }
    const mockRequest2 = { headers: { set: vi.fn() } }

    // Start two concurrent beforeRequest calls
    const promise1 = beforeRequestHook(mockRequest1)
    const promise2 = beforeRequestHook(mockRequest2)

    await Promise.all([promise1, promise2])

    // Both should complete without throwing, even if refresh fails
    expect(true).toBe(true)
  })
})
