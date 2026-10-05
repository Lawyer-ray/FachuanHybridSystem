/**
 * 通行密钥（Passkey/WebAuthn）API。
 *
 * 端点契约见 backend/apps/social_auth/api/passkey_api.py。两个客户端的分工
 * 与 social-api.ts 完全一致：挑战存 Django session cookie，预登录的 login/*
 * 用无 JWT 但带同源 cookie 的客户端；register/* 与凭据管理要求 JWT。
 * 业务失败一律 HTTP 200 + { success: false, message }，在此 throw 交给调用方。
 */
import ky, { type KyInstance } from 'ky'
import { createApiClient } from '@/lib/api'
import { setTokens } from '@/lib/token'
import type { components } from '@/types/api-schema'
import type {
  AssertionResponseJSON,
  PasskeyCreationOptionsJSON,
  PasskeyRequestOptionsJSON,
  RegistrationResponseJSON,
} from './passkey-coding'

const passkeyClient: KyInstance = ky.create({ credentials: 'same-origin', retry: 0 })
const authedClient = createApiClient({ credentials: 'same-origin', retry: 0 })

/** ceremony 选项响应（public_key 为浏览器可直用的 WebAuthn Options JSON） */
export interface PasskeyOptionsResponse {
  success: boolean
  message: string
  public_key: Record<string, unknown> | null
}

/** 已注册通行密钥的展示行（不含公钥等内部字段） */
export interface PasskeyCredentialRow {
  id: number
  name: string
  rp_id: string
  created_at: string
  last_used_at: string | null
}

type TokenExchangeResponse = components['schemas']['TokenExchangeOut']

/** 凭据列表的 query key（与 BINDINGS_KEY 同层） */
export const PASSKEY_CREDENTIALS_KEY = ['passkey-credentials'] as const

/** 统一拆信封：success:false 视为业务错误并 throw */
async function unwrap<T extends { success: boolean; message: string }>(
  promise: Promise<T>,
  fallback: string,
): Promise<T> {
  const data = await promise
  if (!data.success) throw new Error(data.message || fallback)
  return data
}

export const passkeyApi = {
  /** 登录挑战（无需登录态）。 */
  async loginOptions(): Promise<PasskeyRequestOptionsJSON> {
    const data = await unwrap(
      passkeyClient.post('/api/v1/social/passkey/login/options').json<PasskeyOptionsResponse>(),
      '通行密钥暂不可用',
    )
    return (data.public_key ?? {}) as unknown as PasskeyRequestOptionsJSON
  },

  /** 登录验证。token 落 localStorage 是 API 层的责任（与 exchangeToken 同一约定）。 */
  async loginVerify(credential: AssertionResponseJSON): Promise<TokenExchangeResponse> {
    const data = await passkeyClient
      .post('/api/v1/social/passkey/login/verify', { json: { credential } })
      .json<TokenExchangeResponse>()
    if (data.success && data.access && data.refresh) {
      setTokens({ access: data.access, refresh: data.refresh })
    }
    return data
  },

  /** 注册挑战（需登录）。 */
  async registerOptions(): Promise<PasskeyCreationOptionsJSON> {
    const data = await unwrap(
      authedClient.post('social/passkey/register/options').json<PasskeyOptionsResponse>(),
      '通行密钥暂不可用',
    )
    return (data.public_key ?? {}) as unknown as PasskeyCreationOptionsJSON
  },

  /** 注册验证，返回新凭据的展示信息。 */
  async registerVerify(credential: RegistrationResponseJSON): Promise<PasskeyCredentialRow> {
    const data = await authedClient
      .post('social/passkey/register/verify', { json: { name: '', credential } })
      .json<{ success: boolean; message: string; credential: PasskeyCredentialRow | null }>()
    if (!data.success || !data.credential) {
      throw new Error(data.message || '通行密钥注册失败')
    }
    return data.credential
  },

  /** 当前用户已注册的通行密钥。 */
  async list(): Promise<PasskeyCredentialRow[]> {
    const data = await authedClient
      .get('social/passkey/credentials')
      .json<{ credentials: PasskeyCredentialRow[] }>()
    return data.credentials ?? []
  },

  /** 重命名。 */
  async rename(id: number, name: string): Promise<void> {
    await unwrap(
      authedClient.patch(`social/passkey/credentials/${id}`, { json: { name } }).json<{ success: boolean; message: string }>(),
      '重命名失败',
    )
  },

  /** 删除 = 吊销该设备。 */
  async remove(id: number): Promise<void> {
    await unwrap(
      authedClient.delete(`social/passkey/credentials/${id}`).json<{ success: boolean; message: string }>(),
      '删除失败',
    )
  },
}
