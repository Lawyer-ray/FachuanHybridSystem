import {
  getAccessToken,
  getRefreshToken,
  setTokens,
  clearTokens,
  hasToken,
  parseJwtPayload,
  isTokenExpired,
  shouldRefreshToken,
} from '../token'

// localStorage mock is provided by jsdom

beforeEach(() => {
  localStorage.clear()
})

describe('getAccessToken / getRefreshToken', () => {
  it('returns null when no token stored', () => {
    expect(getAccessToken()).toBeNull()
    expect(getRefreshToken()).toBeNull()
  })

  it('returns stored token', () => {
    localStorage.setItem('access_token', 'abc')
    localStorage.setItem('refresh_token', 'def')
    expect(getAccessToken()).toBe('abc')
    expect(getRefreshToken()).toBe('def')
  })
})

describe('setTokens', () => {
  it('stores tokens in localStorage', () => {
    setTokens({ access: 'new-access', refresh: 'new-refresh' })
    expect(localStorage.getItem('access_token')).toBe('new-access')
    expect(localStorage.getItem('refresh_token')).toBe('new-refresh')
  })
})

describe('clearTokens', () => {
  it('removes tokens from localStorage', () => {
    localStorage.setItem('access_token', 'abc')
    localStorage.setItem('refresh_token', 'def')
    clearTokens()
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })
})

describe('hasToken', () => {
  it('returns false when no token', () => {
    expect(hasToken()).toBe(false)
  })

  it('returns true when token exists', () => {
    localStorage.setItem('access_token', 'abc')
    expect(hasToken()).toBe(true)
  })
})

describe('parseJwtPayload', () => {
  it('parses a valid JWT payload', () => {
    // Create a valid JWT: header.payload.signature
    const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }))
    const payload = btoa(JSON.stringify({ sub: 1, exp: 9999999999 }))
    const token = `${header}.${payload}.sig`
    const result = parseJwtPayload(token)
    expect(result).toEqual({ sub: 1, exp: 9999999999 })
  })

  it('returns null for invalid token', () => {
    expect(parseJwtPayload('invalid')).toBeNull()
  })

  it('returns null for empty string', () => {
    expect(parseJwtPayload('')).toBeNull()
  })

  it('handles base64url encoding', () => {
    const header = btoa(JSON.stringify({ alg: 'HS256' }))
    // Use base64url chars: +/ → -_
    const payloadB64 = btoa(JSON.stringify({ data: 'test' }))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
    const token = `${header}.${payloadB64}.sig`
    const result = parseJwtPayload(token)
    expect(result).toEqual({ data: 'test' })
  })
})

describe('isTokenExpired', () => {
  it('returns true for invalid token', () => {
    expect(isTokenExpired('invalid')).toBe(true)
  })

  it('returns true for expired token', () => {
    const header = btoa(JSON.stringify({ alg: 'HS256' }))
    const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) - 100 }))
    const token = `${header}.${payload}.sig`
    expect(isTokenExpired(token)).toBe(true)
  })

  it('returns false for valid token', () => {
    const header = btoa(JSON.stringify({ alg: 'HS256' }))
    const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 }))
    const token = `${header}.${payload}.sig`
    expect(isTokenExpired(token)).toBe(false)
  })

  it('returns true for token without exp', () => {
    const header = btoa(JSON.stringify({ alg: 'HS256' }))
    const payload = btoa(JSON.stringify({ sub: 1 }))
    const token = `${header}.${payload}.sig`
    expect(isTokenExpired(token)).toBe(true)
  })
})

describe('shouldRefreshToken', () => {
  it('returns false when no token', () => {
    expect(shouldRefreshToken()).toBe(false)
  })

  it('returns true for expired token', () => {
    const header = btoa(JSON.stringify({ alg: 'HS256' }))
    const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) - 100 }))
    localStorage.setItem('access_token', `${header}.${payload}.sig`)
    expect(shouldRefreshToken()).toBe(true)
  })

  it('returns false for valid token', () => {
    const header = btoa(JSON.stringify({ alg: 'HS256' }))
    const payload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) + 3600 }))
    localStorage.setItem('access_token', `${header}.${payload}.sig`)
    expect(shouldRefreshToken()).toBe(false)
  })
})

describe('setTokens - native notification', () => {
  let originalWindow: typeof globalThis & Record<string, unknown>

  beforeEach(() => {
    originalWindow = globalThis as unknown as typeof globalThis & Record<string, unknown>
  })

  afterEach(() => {
    // Restore original window state
    delete (window as unknown as Record<string, unknown>).webkit
  })

  it('calls nativeAuth.postMessage when in macOS WebView', () => {
    const mockPostMessage = vi.fn()
    Object.defineProperty(window, 'webkit', {
      value: {
        messageHandlers: {
          nativeAuth: {
            postMessage: mockPostMessage,
          },
        },
      },
      writable: true,
      configurable: true,
    })

    setTokens({ access: 'new-access', refresh: 'new-refresh' })

    expect(mockPostMessage).toHaveBeenCalledWith({
      type: 'tokenUpdate',
      access: 'new-access',
      refresh: 'new-refresh',
    })
  })

  it('does not throw when webkit is not available', () => {
    delete (window as unknown as Record<string, unknown>).webkit

    expect(() => {
      setTokens({ access: 'a', refresh: 'b' })
    }).not.toThrow()
  })
})

describe('clearTokens - native notification', () => {
  afterEach(() => {
    delete (window as unknown as Record<string, unknown>).webkit
  })

  it('calls nativeAuth.postMessage with logout type when in macOS WebView', () => {
    const mockPostMessage = vi.fn()
    Object.defineProperty(window, 'webkit', {
      value: {
        messageHandlers: {
          nativeAuth: {
            postMessage: mockPostMessage,
          },
        },
      },
      writable: true,
      configurable: true,
    })

    clearTokens()

    expect(mockPostMessage).toHaveBeenCalledWith({
      type: 'logout',
    })
  })

  it('does not throw when webkit is not available', () => {
    delete (window as unknown as Record<string, unknown>).webkit

    expect(() => {
      clearTokens()
    }).not.toThrow()
  })
})
