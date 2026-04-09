/**
 * API Client
 * 通用 API 客户端，带 JWT 认证
 */

import ky, { type KyInstance, type Options } from 'ky'

import {
  clearTokens,
  getAccessToken,
  getRefreshToken,
  setTokens,
  shouldRefreshToken,
} from './token'

/**
 * API 基础路径
 */
export const API_BASE_URL = 'http://localhost:8002/api/v1'

/**
 * 后端根地址（用于拼接 media_url 等相对路径）
 */
export const BACKEND_URL = 'http://localhost:8002'

/**
 * 将后端返回的相对路径转为完整 URL
 */
export function resolveMediaUrl(url: string | null): string | null {
  if (!url) return null
  if (url.startsWith('http')) return url
  return `${BACKEND_URL}${url}`
}

/**
 * Token 刷新响应
 */
interface TokenRefreshResponse {
  access: string
}

/**
 * 是否正在刷新 token
 */
let isRefreshing = false
let refreshPromise: Promise<string | null> | null = null

/**
 * 刷新 access token
 */
async function refreshAccessToken(): Promise<string> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) {
    throw new Error('No refresh token')
  }

  const response = await ky
    .post(`${API_BASE_URL}/token/refresh`, {
      json: { refresh: refreshToken },
    })
    .json<TokenRefreshResponse>()

  setTokens({
    access: response.access,
    refresh: refreshToken,
  })

  return response.access
}

/**
 * 获取有效的 access token
 */
async function getValidAccessToken(): Promise<string | null> {
  const token = getAccessToken()
  if (!token) return null

  if (shouldRefreshToken()) {
    if (isRefreshing && refreshPromise) {
      return refreshPromise
    }

    isRefreshing = true
    refreshPromise = refreshAccessToken()
      .catch(() => {
        clearTokens()
        return null
      })
      .finally(() => {
        isRefreshing = false
        refreshPromise = null
      })

    return refreshPromise
  }

  return token
}

/**
 * 创建带 JWT 认证的 API 客户端
 */
export function createApiClient(options?: Options): KyInstance {
  return ky.create({
    prefixUrl: API_BASE_URL,
    ...options,
    hooks: {
      beforeRequest: [
        async (request) => {
          const token = await getValidAccessToken()
          if (token) {
            request.headers.set('Authorization', `Bearer ${token}`)
          }
        },
        ...(options?.hooks?.beforeRequest || []),
      ],
      afterResponse: [
        async (request, _options, response) => {
          if (response.status === 401 && !request.url.includes('/token/')) {
            try {
              const newToken = await refreshAccessToken()
              const retryRequest = new Request(request, {
                headers: new Headers(request.headers),
              })
              retryRequest.headers.set('Authorization', `Bearer ${newToken}`)
              return ky(retryRequest)
            } catch {
              clearTokens()
              window.location.href = '/login'
              throw new Error('Session expired')
            }
          }
          return response
        },
        ...(options?.hooks?.afterResponse || []),
      ],
    },
  })
}

/**
 * 默认 API 客户端实例
 */
export const api = createApiClient()

export default api
