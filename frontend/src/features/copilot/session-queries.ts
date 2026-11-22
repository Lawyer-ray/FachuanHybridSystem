/**
 * 会话列表的 react-query 参数（key / 取数 / 页大小）**只在这里定义**。
 *
 * 为什么必须一处：同一个 key 在 react-query 里只有一份缓存，**先挂载者的 `queryFn`
 * 决定这份缓存有多少条**。原先 `use-active-session` 取 50 条、`use-session-route`
 * 与 `SessionSidebar` 取 100 条，侧栏到底能翻到 100 条还是只有 50 条取决于挂载顺序；
 * 更糟的是 `use-session-route` 用这份列表判「URL 里的会话不存在」，只装了 50 条时
 * 排名 51–100 的**合法老会话**会被当成坏 id 并跳回新对话（贴过来的链接莫名失效）。
 *
 * 各调用点只在此之上追加自己的行为开关（`enabled` / `refetchOnMount` /
 * `refetchInterval`），不再各自决定 key、页大小与取数函数。
 */

import { listSessions } from './api'
import type { CopilotScope } from './types'

/** 会话列表页大小：会话栏 / 路由判据 / 活跃会话共用同一个数 */
export const SESSION_LIST_LIMIT = 100

/** 失效用前缀（改名/删除/本轮结束都按它整体失效） */
export const SESSIONS_QUERY_PREFIX = ['copilot', 'sessions'] as const

/**
 * `scopeKey`：`all` = 全量视图（会话栏、路由判据）；`origin:refId` = 业务范围视图。
 *
 * 必须与 {@link sessionsQueryOptions} 的 `scope` 同源推导（`all` ↔ 不传 scope），
 * 否则 key 与过滤条件会脱钩：两个不同的 scope 命中同一份缓存。
 */
export function sessionsQueryKey(scopeKey: string) {
  return [...SESSIONS_QUERY_PREFIX, scopeKey]
}

/** 会话列表查询：三处调用共用（页大小见 {@link SESSION_LIST_LIMIT}） */
export function sessionsQueryOptions(scopeKey: string, scope?: CopilotScope) {
  return {
    queryKey: sessionsQueryKey(scopeKey),
    // scope 缺省时**不传第二个参数**：侧栏的「始终拉全量」就是靠这个形状表达
    // （传 undefined 与不传在后端等价，但调用形状是既有测试锁定的事实）
    queryFn: () => (scope ? listSessions(SESSION_LIST_LIMIT, scope) : listSessions(SESSION_LIST_LIMIT)),
    staleTime: 30_000,
    retry: false,
  }
}
