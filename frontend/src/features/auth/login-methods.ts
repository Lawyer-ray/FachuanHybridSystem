/**
 * 登录方式注册表。
 *
 * 登录页不写死「飞书扫码」：后端 `/social/providers` 下发当前已启用的方式，
 * 这里把它与「账号密码」合并成统一的 LoginMethod 列表，LoginPage 只按 kind
 * 派发到对应渲染器。以后接入谷歌网页登录（redirect 型）只需后端加配置，
 * 前端不用改登录页。
 */
import type { SocialProviderInfo } from './social-api'

/** 渲染形态：账密表单 / 内嵌二维码 / 整页跳转授权 */
export type LoginMethodKind = 'password' | 'embedded_qr' | 'redirect'

export interface LoginMethod {
  /** `password` 或 Provider 名（如 `feishu`） */
  id: string
  kind: LoginMethodKind
  label: string
  /** 账密方式没有对应的 Provider */
  provider: SocialProviderInfo | null
}

export const PASSWORD_METHOD_ID = 'password'

/** 只认 embedded_qr，其余（含后端将来新增的未知形态）一律按整页跳转处理 */
function toKind(loginMode: string | undefined): LoginMethodKind {
  return loginMode === 'embedded_qr' ? 'embedded_qr' : 'redirect'
}

/** 账号密码永远排第一：它是唯一不依赖第三方配置的兜底入口 */
export function buildLoginMethods(providers: SocialProviderInfo[]): LoginMethod[] {
  return [
    { id: PASSWORD_METHOD_ID, kind: 'password', label: '账号密码', provider: null },
    ...providers.map((provider) => ({
      id: provider.name,
      kind: toKind(provider.login_mode),
      label: provider.display_name || provider.name,
      provider,
    })),
  ]
}
