import type { InboxSourceFilter } from './types'

/**
 * 收件箱落地时默认停在哪个来源档位。
 *
 * ## 为什么默认「邮箱」而不是「全部」
 *
 * 「全部」把邮箱、一张网、法院短信混成一条流，首屏里混着反垃圾告警、研究院
 * 直播通知与法院送达——律师真正每天要先看的是**邮箱**（当事人回传、对方律师
 * 来函、律所内部转发都在这里），法院送达是一天里的第二落点，切一次「一张网」
 * 就到了。默认「全部」等于把筛选工作丢回给使用者。
 *
 * ## 为什么记住「上一次自己选的档位」
 *
 * 只看「进来就是邮箱」会在另一种真实用法上出错：律师整个下午都在「一张网」里
 * 追送达，中间去项目页看一眼再回来——又被弹回邮箱，等于每次都要重按一次。
 * 所以首次进入用默认值，**用户自己点过的档位**在本次会话内记住（模块级变量，
 * 刷新即回到默认；不写 localStorage，避免换人用同一台机器时残留上一个人的习惯）。
 *
 * ## 为什么要区分「自己选的」与「被程序改的」
 *
 * 深链接 `?message=<id>`（首页「待认领款项」的详情）目标消息可能不在当前档位里，
 * `useDeepLinkMessage` 会**放开筛选**去把它找出来（改成 `all`）。那是一次临时的
 * 程序动作，不是律师的选择——如果也记进偏好，他这次会话里每次回到收件箱都会
 * 被钉在「全部」，默认值等于没生效。所以这里导出两个入口：
 * `rememberInboxSource`（用户点击）与纯覆盖（程序改档，不记）。
 */

/** 首次进入收件箱时的档位 */
export const DEFAULT_INBOX_SOURCE: InboxSourceFilter = 'imap'

/** 本次会话内用户自己选过的档位；null = 还没选过（用默认值） */
let lastPicked: InboxSourceFilter | null = null

/** 首屏该用哪一档：用户选过就用他选的，否则用默认值 */
export function resolveInitialInboxSource(): InboxSourceFilter {
  return lastPicked ?? DEFAULT_INBOX_SOURCE
}

/** 记录用户点击的档位（只有「点击」这条路径该调它） */
export function rememberInboxSource(source: InboxSourceFilter): void {
  lastPicked = source
}

/** 清空记忆（登出/换账号、以及测试之间隔离用）：下次进来重新按默认值起步 */
export function resetInboxSourcePreference(): void {
  lastPicked = null
}
