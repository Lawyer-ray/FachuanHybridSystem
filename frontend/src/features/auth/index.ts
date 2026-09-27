/**
 * 登录认证 feature 的对外出口。
 * 其它 feature / app 层只应从这里引，不穿透内部目录。
 */

export { LoginPage } from './LoginPage'
export { SocialCallbackPage } from './SocialCallbackPage'
export { useAuth } from './store'
export { socialAuthApi } from './social-api'
export type { LoginMode, SocialProvider, SocialSession, SocialLoginErrorCode } from './social-types'
