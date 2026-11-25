/**
 * 材料预处理 feature 的对外出口。
 * 其它 feature / app 层只应从这里引，不穿透内部目录。
 */

import { hasToken } from '@/lib/token'

export { DeskPage } from './components/DeskPage'

/**
 * 全局重置材料预处理阅读器状态与 PDF/字节缓存（登出清理用，换账号不得残留
 * 上一账号的材料内容）。走动态 import：这条依赖链上有 pdfjs-dist（~1MB 懒加载
 * chunk），静态引会把整个材料预处理域拖进首屏包（AppNavbar 经 HomePage 进
 * entry chunk）——调用方（AppNavbar）应经本出口调用，不再穿透内部 store 路径。
 *
 * 重置前先把防抖窗口内的最后一次编辑落盘：律师改完最后一个字就点退出时，
 * 那 450ms 内的改动不该被丢掉。**凭证仍在才存得进去**——调用方若已先清 token，
 * 这里只能按丢弃处理（lib/reset-client-state 的顺序调整见交接报告）。
 */
export async function resetMaterialPrepState(): Promise<void> {
  const [store, persistence, inboxSource] = await Promise.all([
    import('./store'),
    import('./draft-persistence'),
    import('./inbox/default-source'),
  ])
  if (hasToken()) await persistence.flushPendingSave()?.catch(() => {})
  store.useReader.getState().resetAll()
  // 收件箱的档位偏好是「本次会话记住用户自己选过的那一档」——换人登录必须清掉，
  // 否则下一个人进来看到的是上一个人习惯的档位（同 reset-client-state 的主旨）
  inboxSource.resetInboxSourcePreference()
}

/**
 * 某案件的核对历史卡（这案核过几次、结论怎么变）。workbench 的案件详情页挂在
 * 每张案件卡下面消费它——跨 feature 只能走本出口：`eslint.config.js` 的
 * `no-restricted-imports` 禁止引本域内部的深路径（只放行 `@/features/<name>`）。
 */
export { CaseVerifyCard } from './doc-verify/CaseVerifyCard'

/**
 * 后端收件箱消息（/inbox）的行类型。home 的收件箱卡消费同一端点，
 * 经此出口复用（Pick 投影见 features/home/api/inbox.ts），避免两份手抄漂移。
 */
export type { InboxMessage } from './types'

/**
 * 单条收件箱消息的就地详情（正文 + 附件 + 进材料预处理/转材料包）。
 *
 * 首页收件箱卡的「点一行就地展开」消费它：那里的消息就是 InboxMessageOut，
 * 与收件箱页的行同形，因此直接复用 `InboxRow`，不另设一套投影类型。
 * 抽屉外壳（MessageDrawer）不对外——首页展开是手风琴，不是滑出抽屉。
 */
export { MessageContent as InboxMessageContent } from './inbox'
export type { MessageContentRow } from './inbox'
