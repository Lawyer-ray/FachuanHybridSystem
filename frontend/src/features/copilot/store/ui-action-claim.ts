/**
 * 多标签页执行权抢占：同一条 `ui_action` 只让一个标签页执行。
 *
 * ## 为什么必须抢占
 *
 * 同一会话开两个标签页时，同一条 SSE `ui_action` 帧**两边都收得到**，而
 * `store/ui-tools.ts` 里的 `seenCallIds` 是模块级的、每个标签页各一份——它挡得住
 * 自己收到重放，挡不住对面那个标签页。后果不是「白跳一下」：`confirm` / `guarded`
 * 的执行器是 read-modify-write（`setPackStatusRemote` 先 `getPackDetail` 再整体
 * `saveDraft`），两个标签页各执行一次就是两次写库、还可能丢更新，而两条回执各说各的。
 * 收敛手段里最便宜的是**先抢占**：谁先在 `localStorage` 写下「这条 callId 归我」，
 * 谁执行。对照 OpenAI Apps SDK 的 `widgetSessionId`（标识「当前挂载的那一份页面实例」），
 * 我们这里用的是「同一个 callId 横跨页面实例只能有一个执行者」。
 *
 * ## 为什么抢不到时**不回执**
 *
 * 回执是模型唯一的注入点（工具返回值），它是「这条动作到底成了没成」的**唯一**答案。
 * 抢到的那个标签页会发；抢不到的这个再发一份，后端只会看到自相矛盾的两个结局
 * （先 ok 后 denied，或先 ok 后超时），模型据此重发一次写动作。所以抢不到就静默返回：
 * 不落运行记录、不回执、不弹提示——横幅也不该在没执行的标签页上报「AI 正在操作」。
 *
 * ## 为什么 TTL 是 15 秒
 *
 * 下界：写动作排队上限 `MAX_WRITE_QUEUE = 3` 个 × 毫秒级执行 + 一次写库往返，任何
 * 真实执行都远在 15 秒内完成，所以不会误抢别人正在做的事。上界：远小于律师察觉
 * 「卡住了」的阈值，标签页崩溃 / 被关掉之后，同一条动作最多 15 秒就能被别的标签页
 * 接手——过期即失效，崩溃的标签页不许永久占着。
 *
 * 本模块刻意零依赖（不引 React、不引 store）：它要能被 node 单测直接 import，也不给
 * 「抢占 → store → 执行层」留一条回头路。
 */

/** 抢占键前缀：一个 callId 一条，值是抢占时刻（毫秒时间戳） */
export const CLAIM_PREFIX = 'fachuan:ui-action-claim:'

/** 抢占存活时长（毫秒）：超过即视为「那个标签页不在飞这条动作了」（理由见文件头） */
export const CLAIM_TTL_MS = 15_000

/** 「拿不到 localStorage」只 warn 一次：隐私模式下每个动作都刷一条会把控制台淹掉 */
let warnedUnavailable = false

/** `Storage` 只用得到的三个方法（测试给的是 `Map` 包一层的假货，不必造整个 Storage） */
export type ClaimStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

/** 注入点：生产走 `globalThis.localStorage` 与 `Date.now()`，单测注入假 storage / 假时钟 */
export interface ClaimPorts {
  now?: () => number
  storage?: ClaimStorage
}

/**
 * 抢占一次执行权：`true` = 本标签页拿到执行权（照常执行）；`false` = 别的标签页已经
 * 抢到这条 callId（调用方应静默返回，见文件头）。
 *
 * **只给 `store/ui-tools.ts` 的 `runUiAction` 用**（导出是为了单测）：别处调用会凭空
 * 抢走另一个标签页的执行权。
 *
 * 拿不到 `localStorage`（Safari 隐私模式下连读属性都抛 / node 环境没有这个全局）时
 * 返回 `true` 并照常执行：宁可重复执行，也不能什么都不做——代价是这种情况下不拦重复。
 */
export function claimUiActionExecution(callId: string, ports: ClaimPorts = {}): boolean {
  const now = (ports.now ?? Date.now)()
  const key = CLAIM_PREFIX + callId
  try {
    const storage = ports.storage ?? globalThis.localStorage
    // 读到的值可能是脏的（`Number(null)` / `Number('')` 都是 0，`'abc'` 是 NaN），
    // 一律按「没有有效抢占」处理：`held > 0` 把 1970 年挡在真实时间戳之外，
    // `Number.isFinite` 挡掉 NaN / Infinity。
    const held = Number(storage.getItem(key))
    if (Number.isFinite(held) && held > 0 && now - held < CLAIM_TTL_MS) return false
    // 过期键当场删掉再写（removeItem 对不存在的键是空操作）：崩溃 / 关掉的标签页
    // 不许永久占着这条动作。只清本条 callId 的键，不遍历整个 localStorage——每次
    // 动作都做一遍全表扫描不值当，别的 callId 的残留也挡不住任何人（TTL 一到即失效）。
    storage.removeItem(key)
    storage.setItem(key, String(now))
    return true
  } catch {
    if (!warnedUnavailable) {
      warnedUnavailable = true
      console.warn('[ui-action-claim] 本页拿不到 localStorage：多标签页抢占失效，动作照常执行')
    }
    return true
  }
}
