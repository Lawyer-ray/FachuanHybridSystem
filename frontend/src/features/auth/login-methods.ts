/**
 * 登录方式注册表。
 *
 * 登录页不写死「飞书扫码」：后端 `/social/providers` 下发当前已启用的方式，
 * 这里把它与「账号密码」合并成两组——按钮型（redirect）与账密同页堆叠，
 * 扫码型（embedded_qr）独立成一个「扫码登录」标签页。以后接入新的
 * redirect 型（微软设备码）/ 扫码型（微信）登录只需后端加配置，前端不用改。
 */
import type { LoginMethod, LoginMethodKind, SocialProviderInfo } from './types'

/** LoginMethod / LoginMethodKind 定义在 `types.ts`，此处 re-export 保持既有 import 路径 */
export type { LoginMethod, LoginMethodKind }

export const PASSWORD_METHOD_ID = 'password'
export const QR_METHOD_ID = 'qr'

/** 非空数组：把「至少一个元素」编码进类型，让 [0] 在 noUncheckedIndexedAccess 下无需判空 */
export type NonEmptyArray<T> = [T, ...T[]]

/** 带 Provider 的登录方式：分组结果里 provider 恒存在，调用方免判空 */
export type SocialLoginMethod = LoginMethod & { provider: SocialProviderInfo }

/** 分组结果：账密恒存在（唯一不依赖第三方配置的兜底入口），两组按后端下发顺序排列 */
export interface LoginMethodGroups {
  password: LoginMethod
  /** 整页跳转授权型（GitHub、Google…）：渲染为账密表单下方的按钮堆叠 */
  redirectProviders: SocialLoginMethod[]
  /** 内嵌二维码型（飞书…）：渲染为独立的「扫码登录」标签页 */
  qrProviders: SocialLoginMethod[]
}

/** 只认 embedded_qr，其余（含后端将来新增的未知形态）一律按整页跳转处理 */
function toKind(loginMode: string | undefined): LoginMethodKind {
  return loginMode === 'embedded_qr' ? 'embedded_qr' : 'redirect'
}

function toSocialMethod(provider: SocialProviderInfo): SocialLoginMethod {
  return {
    id: provider.name,
    kind: toKind(provider.login_mode),
    label: provider.display_name || provider.name,
    provider,
  }
}

export function buildLoginMethodGroups(providers: SocialProviderInfo[]): LoginMethodGroups {
  const redirectProviders: SocialLoginMethod[] = []
  const qrProviders: SocialLoginMethod[] = []
  for (const provider of providers) {
    const method = toSocialMethod(provider)
    ;(method.kind === 'embedded_qr' ? qrProviders : redirectProviders).push(method)
  }
  return {
    password: { id: PASSWORD_METHOD_ID, kind: 'password', label: '账号密码', provider: null },
    redirectProviders,
    qrProviders,
  }
}
