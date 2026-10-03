/**
 * 材料预处理 feature 的对外出口。
 * 其它 feature / app 层只应从这里引，不穿透内部目录。
 */

export { DeskPage } from './components/DeskPage'

/**
 * 后端收件箱消息（/inbox）的行类型。home 的收件箱卡消费同一端点，
 * 经此出口复用（Pick 投影见 features/home/api/inbox.ts），避免两份手抄漂移。
 */
export type { InboxMessage } from './types'
