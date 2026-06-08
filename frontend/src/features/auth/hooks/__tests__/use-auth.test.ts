vi.mock('@/stores/auth', () => {
  const mockLogin = vi.fn()
  const mockLogout = vi.fn()
  const mockCheckAuth = vi.fn()
  const storeState = {
    user: null,
    isAuthenticated: false,
    isAdmin: false,
    isLoading: false,
    login: mockLogin,
    logout: mockLogout,
    checkAuth: mockCheckAuth,
  }
  return {
    useAuthStore: vi.fn((selector: Function) => selector(storeState)),
    selectUser: (s: any) => s.user,
    selectIsAuthenticated: (s: any) => s.isAuthenticated,
    selectIsAdmin: (s: any) => s.isAdmin,
    selectIsLoading: (s: any) => s.isLoading,
    __mocks: { mockLogin, mockLogout, mockCheckAuth },
  }
})

import { renderHook } from '@testing-library/react'
import { useAuth } from '../use-auth'
import { useAuthStore } from '@/stores/auth'

describe('useAuth', () => {
  it('returns default auth state when not logged in', () => {
    const { result } = renderHook(() => useAuth())
    expect(result.current.user).toBeNull()
    expect(result.current.isAuthenticated).toBe(false)
    expect(result.current.isAdmin).toBe(false)
    expect(result.current.isLoading).toBe(false)
  })

  it('exposes login, logout and checkAuth actions', () => {
    const { result } = renderHook(() => useAuth())
    expect(typeof result.current.login).toBe('function')
    expect(typeof result.current.logout).toBe('function')
    expect(typeof result.current.checkAuth).toBe('function')
  })

  it('calls useAuthStore with selectors', () => {
    renderHook(() => useAuth())
    expect(useAuthStore).toHaveBeenCalled()
  })
})
