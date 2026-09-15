/**
 * Auth Feature API：简单的用户名/密码登录，拿 JWT。
 */
import ky from 'ky'
import { api, API_BASE_URL } from '@/lib/api'
import { setTokens } from '@/lib/token'
import type { LoginRequest, TokenPair, User } from './types'

export const authApi = {
  async login(data: LoginRequest): Promise<{ success: boolean; user?: User; message?: string }> {
    let tokenPair: TokenPair
    try {
      tokenPair = await ky.post(`${API_BASE_URL}/token/pair`, { json: data }).json<TokenPair>()
    } catch (e) {
      const message = e instanceof Error ? '用户名或密码错误' : '登录失败'
      return { success: false, message }
    }
    setTokens(tokenPair)
    try {
      const user = await api.get('organization/me').json<User>()
      return { success: true, user }
    } catch {
      return { success: true }
    }
  },
}
