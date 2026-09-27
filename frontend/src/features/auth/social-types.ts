/**
 * 社交登录类型。
 */

/** 登录方式的交互形态，后端 /social/providers 下发。 */
export type LoginMode = 'redirect' | 'embedded_qr'

export interface SocialProvider {
  name: string
  display_name: string
  /** redirect：跳转到授权页；embedded_qr：前端渲染二维码 */
  login_mode: LoginMode
  /** 渲染所需的公开信息（app_id / authorize_url / 二维码尺寸），不含密钥 */
  client_config: {
    app_id?: string
    authorize_url?: string
    scope?: string
    width?: string
    height?: string
    [k: string]: string | undefined
  } | null
}

export interface SocialSession {
  /** 拼上 tmp_code 后即可完成跳转的授权页地址 */
  goto: string
  state: string
  expires_in: number
}

export interface SocialTokenExchangeResponse {
  success: boolean
  access?: string
  refresh?: string
  user?: import('./types').User
  message?: string
}

/** 扫码面板对外暴露的动作，便于上层控制显隐。 */
export type SocialLoginErrorCode =
  | 'no_session'
  | 'invalid_session'
  | 'invalid_state'
  | 'state_expired'
  | 'provider_denied'
  | 'no_code'
  | 'unknown_provider'
  | 'exchange_failed'
  | 'network_error'
  | 'missing_code'
  | 'expired_code'
  // 绑定流程专用：登录只放行已绑定身份，绑定冲突也在这里反馈
  | 'unbound'
  | 'not_bound'
  | 'already_bound'
  | 'provider_occupied'

export const SOCIAL_LOGIN_ERROR_TEXT: Record<SocialLoginErrorCode, string> = {
  no_session: '登录会话已失效，请重新扫码',
  invalid_session: '登录会话异常，请重新扫码',
  invalid_state: '安全校验失败，请重新扫码',
  state_expired: '二维码已过期，请刷新后重试',
  provider_denied: '你取消了授权',
  no_code: '未获取到授权码，请重试',
  unknown_provider: '该登录方式暂不可用',
  exchange_failed: '登录失败，请稍后重试',
  network_error: '网络异常，请检查连接后重试',
  missing_code: '回调参数缺失，请重新扫码',
  expired_code: '授权码已过期，请重新扫码',
  unbound: '该社交账号尚未绑定律师，请先用账号密码登录，再到「账号绑定」完成绑定',
  not_bound: '绑定失败：登录状态已失效，请重新登录后再绑定',
  already_bound: '该社交账号已绑定其他律师，请先让其解绑',
  provider_occupied: '你已绑定该平台的另一个账号，请先解绑再绑定新账号',
}
