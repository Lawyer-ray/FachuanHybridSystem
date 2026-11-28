/**
 * 界面动作的幂等与同参去重（从 `store/ui-tools.ts` 拆出的执行期守卫第一档）。
 *
 * 调用点仍在 `store/ui-tools.ts` 的 `runUiAction` / `runOne`（去重要在**排队之前**挡，
 * 理由见那里的注释）；本文件只收口「这条动作是不是重复投递」这一件事。
 *
 * ## 为什么按 callId 幂等
 *
 * 同一 callId 只执行一次：模型重试与事件重放都会再来一遍。重复导航只是白跳一下，
 * 重复执行一次写库动作就是事故，所以从第一档起就按最严的口径挡。
 * 重复投递不回执：第一次投递已经发过，再发一遍只会让后端的 pending 表多一条假结算。
 *
 * ## 非幂等动作的同参 5 秒窗
 *
 * 非幂等动作的同参重试按 5 秒窗挡掉（08 §6）。命中就静默丢：它本来就是「同一次
 * 操作被重发」，再弹一次错误提示反而制造噪音。
 * 也不回执：这一次**什么都没执行**，回 ok 是撒谎，而契约里没有「已去重」这个码。
 *
 * ## 为什么去重表在模块级而不是 state
 *
 * `seenCallIds` 与「非幂等动作的同参 5 秒窗」只服务执行期守卫，没有组件要订阅它们；
 * 放进 `CopilotState` 的代价是每次动作都触发一遍全局订阅者比较。
 */

/** 幂等键 LRU 上限（08 §6）：够覆盖一轮长对话的重放，又不会无界增长 */
const SEEN_CALLID_LIMIT = 200
/** 非幂等动作的同参去重窗口（08 §6）：模型重试与「律师真想再点一次」只能靠时间区分 */
const NON_IDEMPOTENT_WINDOW_MS = 5_000

/** 已受理过的 callId（LRU：Set 保持插入序，超限时删最旧的） */
const seenCallIds = new Set<string>()
/** 非幂等动作最近一次执行时刻（键 = 动作名 + 稳定序列化参数） */
const recentNonIdempotent = new Map<string, number>()

/** 稳定序列化：键排序后再序列化，参数书写顺序不同不该算成两个不同的动作 */
function stableKey(action: string, args: Record<string, unknown>): string {
  const pairs = Object.keys(args)
    .sort()
    .map((key) => [key, args[key]] as const)
  return `${action}:${JSON.stringify(pairs)}`
}

/** 记一次 callId；返回 true = 之前已见过（重复投递 / 事件重放） */
export function rememberCallId(callId: string): boolean {
  if (seenCallIds.has(callId)) return true
  seenCallIds.add(callId)
  if (seenCallIds.size > SEEN_CALLID_LIMIT) {
    const oldest = seenCallIds.values().next().value
    if (oldest !== undefined) seenCallIds.delete(oldest)
  }
  return false
}

/** 非幂等动作的同参去重：true = 允许执行（顺带清掉过窗的旧记录，Map 才不胀） */
export function allowNonIdempotent(action: string, args: Record<string, unknown>, now: number): boolean {
  for (const [key, at] of recentNonIdempotent) {
    if (now - at > NON_IDEMPOTENT_WINDOW_MS) recentNonIdempotent.delete(key)
  }
  const key = stableKey(action, args)
  const last = recentNonIdempotent.get(key)
  if (last !== undefined && now - last <= NON_IDEMPOTENT_WINDOW_MS) return false
  recentNonIdempotent.set(key, now)
  return true
}
