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
 * 获取 API 基础路径（localStorage 优先，fallback 到环境变量）。
 *
 * 默认用**相对路径** `/api/v1`：dev 由 Vite proxy 转发到后端，生产按同源部署，
 * 都不需要写死 host。（社交登录的 session cookie 也要求与后端同源，见
 * features/auth/social-api.ts 的说明——整站统一同源约定，避免两套 URL 体系。）
 * localStorage 里若被 Native 壳等宿主写入了 api_base_url，仍然优先生效。
 */
export function getApiBaseUrl(): string {
  return localStorage.getItem('api_base_url') || import.meta.env.VITE_API_BASE_URL || '/api/v1'
}

/** 模块级缓存，避免每次调用都读 localStorage */
export const API_BASE_URL = getApiBaseUrl()

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
    prefix: API_BASE_URL,
    ...options,
    hooks: {
      beforeRequest: [
        async ({ request }) => {
          const token = await getValidAccessToken()
          if (token) {
            request.headers.set('Authorization', `Bearer ${token}`)
          }
        },
        ...(options?.hooks?.beforeRequest || []),
      ],
      afterResponse: [
        async ({ request, response }) => {
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
