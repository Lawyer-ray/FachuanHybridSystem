/**
 * auth 域常量：社交登录错误码与文案、外部资源地址、query key。
 * （此前常量散落在类型文件与组件里，按规范收敛到 constants.ts。）
 */

/** 登录方式的交互形态，后端 /social/providers 下发 */
export type LoginMode = 'redirect' | 'embedded_qr'

/** 扫码面板对外暴露的错误码（后端回调 error 参数的已知取值） */
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

/** 飞书扫二维码登录 SDK（官方固定 CDN 地址） */
export const FEISHU_QR_SDK_URL =
  'https://lf-package-cn.feishucdn.com/obj/feishu-static/lark/passport/qrcode/LarkSSOSDKWebQRCode-1.0.3.js'

/** 账号绑定页的 query key */
export const BINDINGS_KEY = ['social-bindings'] as const
export const CATALOG_KEY = ['social-provider-catalog'] as const
