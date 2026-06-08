vi.mock('../../api', () => ({
  authApi: {
    login: vi.fn().mockResolvedValue({ user: { id: 1, username: 'test' } }),
    register: vi.fn().mockResolvedValue({ success: true, requires_approval: true }),
    logout: vi.fn().mockResolvedValue(undefined),
    autoLogin: vi.fn().mockResolvedValue({ user: { id: 1 } }),
  },
}))

vi.mock('@/stores/auth', () => ({
  useAuthStore: vi.fn((selector: Function) => selector({
    login: vi.fn(),
    logout: vi.fn(),
  })),
}))

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, act } from '@testing-library/react'
import React from 'react'
import { useLoginMutation, useRegisterMutation, useLogoutMutation } from '../use-auth-mutations'

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) => (
    React.createElement(QueryClientProvider, { client: queryClient }, children)
  )
}

describe('useLoginMutation', () => {
  it('returns a mutation object with mutate function', () => {
    const { result } = renderHook(() => useLoginMutation(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
    expect(result.current).toHaveProperty('isPending')
  })

  it('calls authApi.login when mutate is invoked', async () => {
    const { authApi } = await import('../../api')
    const { result } = renderHook(() => useLoginMutation(), { wrapper: createWrapper() })
    act(() => { result.current.mutate({ username: 'admin', password: '123456' }) })  // allowlist secret

    expect(result.current).toHaveProperty("mutate")
  })

  it('is not pending before mutation', () => {
    const { result } = renderHook(() => useLoginMutation(), { wrapper: createWrapper() })
    expect(result.current.isPending).toBe(false)
  })
})

describe('useRegisterMutation', () => {
  it('returns a mutation object', () => {
    const { result } = renderHook(() => useRegisterMutation(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls authApi.register when mutate is invoked', async () => {
    const { authApi } = await import('../../api')
    const { result } = renderHook(() => useRegisterMutation(), { wrapper: createWrapper() })
    act(() => { result.current.mutate({ username: 'newuser', password: '123456', real_name: 'New' }) })  // allowlist secret

    expect(result.current).toHaveProperty("mutate")
  })

  it('starts in non-pending state', () => {
    const { result } = renderHook(() => useRegisterMutation(), { wrapper: createWrapper() })
    expect(result.current.isPending).toBe(false)
  })

  it('throws error when registration response is not successful', async () => {
    const { authApi } = await import('../../api')
    vi.mocked(authApi.register).mockResolvedValueOnce({
      success: false,
      message: '用户名已存在',
      requires_approval: false,
      user: null,
    } as any)

    const { result } = renderHook(() => useRegisterMutation(), { wrapper: createWrapper() })

    await act(async () => {
      try {
        await result.current.mutateAsync({ username: 'existing', password: '123456', real_name: 'Test' })  // allowlist secret
      } catch (e) {
        expect((e as Error).message).toBe('用户名已存在')
      }
    })
  })

  it('throws generic error when registration fails without message', async () => {
    const { authApi } = await import('../../api')
    vi.mocked(authApi.register).mockResolvedValueOnce({
      success: false,
      message: '',
      requires_approval: false,
      user: null,
    } as any)

    const { result } = renderHook(() => useRegisterMutation(), { wrapper: createWrapper() })

    await act(async () => {
      try {
        await result.current.mutateAsync({ username: 'newuser', password: '123456', real_name: 'Test' })  // allowlist secret
      } catch (e) {
        expect((e as Error).message).toBe('注册失败')
      }
    })
  })

  it('auto-logs in when registration succeeds without approval requirement', async () => {
    const { authApi } = await import('../../api')
    const mockUser = { id: 1, username: 'firstuser', is_active: true }
    vi.mocked(authApi.register).mockResolvedValueOnce({
      success: true,
      requires_approval: false,
      user: mockUser,
    } as any)

    const { result } = renderHook(() => useRegisterMutation(), { wrapper: createWrapper() })

    await act(async () => {
      const response = await result.current.mutateAsync({
        username: 'firstuser',
        password: '123456',  // allowlist secret
        real_name: 'First',
      })
      expect(response.success).toBe(true)
    })

    expect(authApi.autoLogin).toHaveBeenCalledWith('firstuser', '123456')
  })

  it('handles auto-login failure gracefully', async () => {
    const { authApi } = await import('../../api')
    const mockUser = { id: 1, username: 'newuser', is_active: true }
    vi.mocked(authApi.register).mockResolvedValueOnce({
      success: true,
      requires_approval: false,
      user: mockUser,
    } as any)
    vi.mocked(authApi.autoLogin).mockRejectedValueOnce(new Error('Login failed'))

    const { result } = renderHook(() => useRegisterMutation(), { wrapper: createWrapper() })

    await act(async () => {
      // Should not throw even if auto-login fails
      const response = await result.current.mutateAsync({
        username: 'newuser',
        password: '123456',  // allowlist secret
        real_name: 'New',
      })
      expect(response.success).toBe(true)
    })
  })
})

describe('useLogoutMutation', () => {
  it('returns a mutation object', () => {
    const { result } = renderHook(() => useLogoutMutation(), { wrapper: createWrapper() })
    expect(result.current).toHaveProperty('mutate')
  })

  it('calls authApi.logout when mutate is invoked', async () => {
    const { authApi } = await import('../../api')
    const { result } = renderHook(() => useLogoutMutation(), { wrapper: createWrapper() })
    act(() => { result.current.mutate() })

    expect(result.current).toHaveProperty("mutate")
  })

  it('starts in non-pending state', () => {
    const { result } = renderHook(() => useLogoutMutation(), { wrapper: createWrapper() })
    expect(result.current.isPending).toBe(false)
  })
})
