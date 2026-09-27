/**
 * 社交登录回调页的纯逻辑。
 *
 * 从 SocialCallbackPage 抽出来，便于单测（frontend 当前不引 @testing-library，
 * 只测纯函数）。
 */

import { SOCIAL_LOGIN_ERROR_TEXT, type SocialLoginErrorCode } from './social-types'

/** 只允许站内相对路径，拒绝 //evil.com 这类开放重定向 */
export function sanitizeRedirect(raw: string | null): string {
  if (!raw) return '/'
  if (!raw.startsWith('/') || raw.startsWith('//')) return '/'
  return raw
}

/** 把后端回调的 error 参数映射为可读文案；未知错误码统一归一，避免把后端细节透给用户 */
export function resolveCallbackError(error: string | null): string {
  if (!error) return ''
  const code = (error in SOCIAL_LOGIN_ERROR_TEXT ? error : 'exchange_failed') as SocialLoginErrorCode
  return SOCIAL_LOGIN_ERROR_TEXT[code]
}
