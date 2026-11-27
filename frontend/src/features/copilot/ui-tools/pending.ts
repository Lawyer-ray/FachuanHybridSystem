/**
 * 「先跳过去，再由目标页面接着做」的挂起队列。
 *
 * ## 解决什么
 *
 * 模型说「打开材料预处理的待处理并展开筛选」时，动作可能落在**还没挂载**的页面上：
 * 执行器属于那个页面，但页面此刻根本不存在。直接执行 = 对一个不存在的组件做操作
 * （静默无效，律师只看到 AI 说「已经帮你打开了」）；直接丢掉 = 白跳一次。
 * 所以先把请求排到目标路由名下、`navigate` 过去，页面挂载时自己取走执行
 * （消费端：`hooks/use-ui-pending-action`）。
 *
 * ## 为什么是模块级 Map 而不是 store
 *
 * 读者是「目标页面挂载时的 useEffect」，不是任何一次渲染。放进 store 只会多一份订阅
 * 和一次由 `set` 引起的重渲染，而它从不参与渲染。同理不做持久化：它只在一次 SPA
 * 会话内有效，刷新即作废（刷新后页面已经在了，语言模型那一轮指令也早结束了）。
 *
 * ## 为什么有上限
 *
 * 目标页面若因鉴权 / 异常根本没挂载，就没人来取，队列会无界增长（内存泄漏）。
 * 每页封顶 20 条并丢最旧的：最新一条才是律师刚看到的那句指令，保它比保第一条有用。
 * 页面键是清单里的 `route`（有限集合），所以总量也被这一层封住。
 */

import type { UiActionRequest } from './types'

/** 每个 page 最多挂多少条（理由见文件头「为什么有上限」） */
export const MAX_PENDING_PAGE_ACTIONS = 20

/** page → 待执行请求（按入队顺序；未来执行也按这个顺序） */
const pending = new Map<string, UiActionRequest[]>()

/**
 * 入队一条「等 page 挂载后执行」的请求。
 *
 * `page` 必须与后端清单里该动作的 `route` 字面量完全一致（执行器侧的入队点用的就是
 * `spec.route`）：两边拼写不同时页面永远取不到，表现为「跳过去了但什么都没发生」。
 */
export function queuePageAction(page: string, request: UiActionRequest): void {
  const queue = pending.get(page) ?? []
  queue.push(request)
  if (queue.length > MAX_PENDING_PAGE_ACTIONS) {
    queue.splice(0, queue.length - MAX_PENDING_PAGE_ACTIONS)
  }
  pending.set(page, queue)
}

/**
 * 取走某页的全部待执行请求，**取出即清**。
 *
 * 必须清：页面重挂载（StrictMode 双跑、前后台切换再回来）时同一个请求不能被再执行
 * 一次——导航类动作重复执行只是白跳，写类动作重复执行就是事故。
 */
export function takePageActions(page: string): UiActionRequest[] {
  const queue = pending.get(page)
  if (queue === undefined) return []
  pending.delete(page)
  return queue
}
