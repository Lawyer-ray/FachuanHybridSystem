/**
 * Auth Feature API：简单的用户名/密码登录，拿 JWT。
 */
import { HTTPError } from 'ky'
import ky from 'ky'
import { api, API_BASE_URL } from '@/lib/api'
import { errMessage } from '@/lib/errors'
import { setTokens, type TokenPair } from '@/lib/token'
import type { LoginRequest, User } from './types'

export const authApi = {
  async login(data: LoginRequest): Promise<{ success: boolean; user?: User; message?: string }> {
    let tokenPair: TokenPair
    try {
      tokenPair = await ky.post(`${API_BASE_URL}/token/pair`, { json: data }).json<TokenPair>()
    } catch (e) {
      // 401 才是「账号密码不对」；500 / 断网 / 超时另给文案，别一概说成密码错
      if (e instanceof HTTPError && e.response.status === 401) {
        return { success: false, message: '用户名或密码错误' }
      }
      return { success: false, message: errMessage(e, '登录失败，请检查网络后重试') }
    }
    setTokens(tokenPair)
    try {
      const user = await api.get('organization/me').json<User>()
      return { success: true, user }
    } catch {
      // 有 token 即已登录；me 接口偶发失败不阻塞登录，用户名由 AppNavbar 稍后补拉
      return { success: true }
    }
  },
}
