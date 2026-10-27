/**
 * 登录认证 feature 的对外出口。
 * 其它 feature / app 层只应从这里引，不穿透内部目录。
 *
 * 出口只保留实际有外部消费方的符号（页面组件 + useAuth）；
 * social API 客户端与域内类型不对外暴露——外部有需要时再按需加，
 * 避免出现「导出了但全仓无人用」的幽灵出口。
 *
 * BindingsPanel 仅设置页（features/settings）单处消费，走 lazy 出口：
 * 若在这里静态 re-export，设置页对它的静态引用会把整域（含登录页与 auth.css）
 * 钉进设置页 chunk，dynamic import 拆不出独立 chunk（INEFFECTIVE_DYNAMIC_IMPORT）。
 */

import { lazy } from 'react'

export { LoginPage } from './LoginPage'
export { SocialCallbackPage } from './SocialCallbackPage'
export { useAuth } from './store'

/** 登录用户类型（/organization/me 响应的消费投影）：AppNavbar 补拉用户信息时
 *  复用，避免在组件里手写内联形状后与本域 store 的 User 漂移。 */
export type { User } from './types'

/** 账号绑定面板（懒加载组件，消费方需包 Suspense） */
export const BindingsPanelLazy = lazy(() =>
  import('./BindingsPanel').then((m) => ({ default: m.BindingsPanel })),
)
