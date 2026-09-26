import { create } from 'zustand'
import { getAccessToken, clearTokens } from '@/lib/token'
import { authApi } from './api'
import type { User } from './types'

interface AuthState {
  user: User | null
  /** 应用启动时检查是否已有登录态（有 token 即视为已登录） */
  init: () => void
  /** 补写用户信息（刷新页面后 init 只放了空 username 占位，用它回填真实用户名） */
  setUser: (user: User) => void
  login: (username: string, password: string) => Promise<{ ok: boolean; message?: string }>
  logout: () => void
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  init: () => {
    if (getAccessToken() && !useAuth.getState().user) {
      set({ user: { id: 0, username: '' } })
    }
  },
  setUser: (user) => set({ user }),
  login: async (username, password) => {
    const res = await authApi.login({ username, password })
    if (!res.success) {
      return { ok: false, message: res.message || '登录失败' }
    }
    set({ user: res.user || { id: 0, username } })
    return { ok: true }
  },
  logout: () => {
    clearTokens()
    set({ user: null })
  },
}))
