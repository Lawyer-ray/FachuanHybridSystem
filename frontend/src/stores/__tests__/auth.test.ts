import { clearTokens, hasToken } from '@/lib/token'
import { authApi } from '@/features/auth/api'

vi.mock('@/features/auth/api', () => ({
  authApi: {
    getCurrentUser: vi.fn(),
  },
}))

vi.mock('@/lib/token', () => ({
  clearTokens: vi.fn(),
  hasToken: vi.fn(() => false),
}))

// Use dynamic import to get a fresh store for each test suite
// The store's checkPromise closure prevents proper test isolation otherwise
let useAuthStore: ReturnType<typeof import('../auth')['useAuthStore']>
let selectIsAdmin: typeof import('../auth')['selectIsAdmin']
let selectIsAuthenticated: typeof import('../auth')['selectIsAuthenticated']
let selectUser: typeof import('../auth')['selectUser']
let selectIsLoading: typeof import('../auth')['selectIsLoading']

beforeEach(async () => {
  vi.clearAllMocks()
  vi.resetModules()
  const mod = await import('../auth')
  useAuthStore = mod.useAuthStore
  selectIsAdmin = mod.selectIsAdmin
  selectIsAuthenticated = mod.selectIsAuthenticated
  selectUser = mod.selectUser
  selectIsLoading = mod.selectIsLoading
})

describe('useAuthStore - basic state', () => {
  it('has correct initial state', () => {
    const state = useAuthStore.getState()
    expect(state.user).toBeNull()
    expect(state.isAuthenticated).toBe(false)
    expect(state.isLoading).toBe(true)
  })

  it('setUser sets user and isAuthenticated', () => {
    const user = { id: 1, username: 'test', is_active: true, is_admin: false } as any
    useAuthStore.getState().setUser(user)
    const state = useAuthStore.getState()
    expect(state.user).toBe(user)
    expect(state.isAuthenticated).toBe(true)
  })

  it('setUser(null) clears user and isAuthenticated', () => {
    useAuthStore.getState().setUser(null)
    const state = useAuthStore.getState()
    expect(state.user).toBeNull()
    expect(state.isAuthenticated).toBe(false)
  })

  it('setUser with inactive user sets isAuthenticated to false', () => {
    const user = { id: 1, username: 'test', is_active: false, is_admin: false } as any
    useAuthStore.getState().setUser(user)
    expect(useAuthStore.getState().isAuthenticated).toBe(false)
  })

  it('login sets user, isAuthenticated, and isLoading=false', () => {
    const user = { id: 1, username: 'test', is_active: true, is_admin: false } as any
    useAuthStore.getState().login(user)
    const state = useAuthStore.getState()
    expect(state.user).toBe(user)
    expect(state.isAuthenticated).toBe(true)
    expect(state.isLoading).toBe(false)
  })

  it('logout clears tokens and resets state', () => {
    useAuthStore.getState().logout()
    expect(clearTokens).toHaveBeenCalled()
    const state = useAuthStore.getState()
    expect(state.user).toBeNull()
    expect(state.isAuthenticated).toBe(false)
    expect(state.isLoading).toBe(false)
  })
})

describe('useAuthStore - checkAuth', () => {
  it('sets isLoading false when no token', async () => {
    vi.mocked(hasToken).mockReturnValue(false)
    await useAuthStore.getState().checkAuth()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.isLoading).toBe(false)
  })

  it('handles API error gracefully', async () => {
    vi.mocked(hasToken).mockReturnValue(true)
    vi.mocked(authApi.getCurrentUser).mockRejectedValue(new Error('unauthorized'))
    await useAuthStore.getState().checkAuth()
    const state = useAuthStore.getState()
    expect(state.isAuthenticated).toBe(false)
    expect(state.isLoading).toBe(false)
    expect(state.user).toBeNull()
  })

  it('fetches user when token exists', async () => {
    const user = { id: 1, username: 'test', is_active: true, is_admin: false }
    vi.mocked(hasToken).mockReturnValue(true)
    vi.mocked(authApi.getCurrentUser).mockResolvedValue(user as any)
    await useAuthStore.getState().checkAuth()
    const state = useAuthStore.getState()
    expect(state.user).toEqual(user)
    expect(state.isAuthenticated).toBe(true)
    expect(state.isLoading).toBe(false)
  })

  it('reuses existing checkPromise when called concurrently', async () => {
    const user = { id: 1, username: 'test', is_active: true, is_admin: false }
    vi.mocked(hasToken).mockReturnValue(true)
    // Create a promise that we can control
    let resolveGetCurrentUser: (value: unknown) => void
    const pendingPromise = new Promise((resolve) => {
      resolveGetCurrentUser = resolve
    })
    vi.mocked(authApi.getCurrentUser).mockReturnValue(pendingPromise as ReturnType<typeof authApi.getCurrentUser>)

    // Start two checkAuth calls simultaneously
    const promise1 = useAuthStore.getState().checkAuth()
    const promise2 = useAuthStore.getState().checkAuth()

    // Resolve the API call
    resolveGetCurrentUser!(user)

    await Promise.all([promise1, promise2])

    const state = useAuthStore.getState()
    expect(state.user).toEqual(user)
    expect(state.isAuthenticated).toBe(true)
    // getCurrentUser should only be called once since the second call reuses the promise
    expect(authApi.getCurrentUser).toHaveBeenCalledTimes(1)
  })
})

describe('selectors', () => {
  const baseState = {
    user: { id: 1, username: 'test', is_active: true, is_admin: true } as any,
    isAuthenticated: true,
    isLoading: false,
    setUser: vi.fn(),
    login: vi.fn(),
    logout: vi.fn(),
    checkAuth: vi.fn(),
  }

  it('selectIsAdmin returns true for admin user', () => {
    expect(selectIsAdmin(baseState)).toBe(true)
  })

  it('selectIsAdmin returns false for non-admin user', () => {
    expect(selectIsAdmin({ ...baseState, user: { ...baseState.user, is_admin: false } })).toBe(false)
  })

  it('selectIsAdmin returns false when user is null', () => {
    expect(selectIsAdmin({ ...baseState, user: null })).toBe(false)
  })

  it('selectIsAuthenticated returns state.isAuthenticated', () => {
    expect(selectIsAuthenticated(baseState)).toBe(true)
    expect(selectIsAuthenticated({ ...baseState, isAuthenticated: false })).toBe(false)
  })

  it('selectUser returns user', () => {
    expect(selectUser(baseState)).toBe(baseState.user)
  })

  it('selectIsLoading returns isLoading', () => {
    expect(selectIsLoading(baseState)).toBe(false)
    expect(selectIsLoading({ ...baseState, isLoading: true })).toBe(true)
  })
})
