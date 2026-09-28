/**
 * 登录认证 feature 的对外出口。
 * 其它 feature / app 层只应从这里引，不穿透内部目录。
 *
 * 出口只保留实际有外部消费方的符号（页面组件 + useAuth）；
 * social API 客户端与域内类型不对外暴露——外部有需要时再按需加，
 * 避免出现「导出了但全仓无人用」的幽灵出口。
 */

export { LoginPage } from './LoginPage'
export { BindingsPage } from './BindingsPage'
export { SocialCallbackPage } from './SocialCallbackPage'
export { useAuth } from './store'
