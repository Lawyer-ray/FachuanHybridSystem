/**
 * 页面状态注册表 —— AI 问「现在页面上是什么」时，这里给出**结构化小快照**。
 *
 * 页面状态只有页面自己知道（哪个 stage、选了哪条、表单填到哪），所以由页面挂载时主动声明
 * （`hooks/use-ui-page-state.ts`），copilot 只读这张表。
 *
 * **按 provider 集合计数**，不是按页名计「挂载次数」：同一页可能同时挂两个实例（面板 + 助手
 * 页、StrictMode 双跑），按页名计数会让先卸载的那个把还活着的实例一起注销。读状态一律容错
 * （页面代码抛错只 warn 并按「没声明」处理）：一次快照失败只该退回 `no_page_state`。
 */

/** 页面声明状态的方式：一个读取函数（读到被问那一刻的最新值，而不是注册时的快照）。 */
export type PageStateProvider = () => Record<string, unknown>

/** 一次成功读取：`page` 是页名，`route` 是读出那一刻的真实地址。 */
export type PageStateRead = { page: string; route: string; state: Record<string, unknown> }

/** 最近一次被问的结果（`state=null` = 没有任何页面声明状态）。 */
export type PageStateAnswer = { page: string | null; route: string; state: Record<string, unknown> | null }

/** 页名 → 已挂载的 provider（Set 保持插入序，最后一个 = 当前实例）；`order` 记注册顺序。 */
const providers = new Map<string, Set<PageStateProvider>>()
const order: string[] = []
const listeners = new Set<(answer: PageStateAnswer) => void>()

/** 读出那一刻的地址（pathname + search）；非浏览器环境返回空串（node 单测）。 */
export function currentRoute(): string {
  return typeof window === 'undefined' ? '' : window.location.pathname + window.location.search
}

/** 页面挂载：登记一个状态提供者（同页多实例各登记各的）。 */
export function registerPageState(page: string, provider: PageStateProvider): void {
  let set = providers.get(page)
  if (!set) providers.set(page, (set = new Set()))
  set.add(provider)
  const at = order.indexOf(page)
  if (at !== -1) order.splice(at, 1)
  order.push(page)
}

/** 页面卸载：注销这个 provider（同页还有别的实例时不摘页名）。 */
export function unregisterPageState(page: string, provider: PageStateProvider): void {
  const set = providers.get(page)
  if (!set) return
  set.delete(provider)
  if (set.size > 0) return
  providers.delete(page)
  const at = order.indexOf(page)
  if (at !== -1) order.splice(at, 1)
}

/**
 * 读页面此刻声明的状态；`page` 缺省 = 最近注册且已挂载的那个页面。返回 `null` = **没有页面
 * 声明状态**：调用方必须明说「没声明」，不许假装 `{}`（空对象会被模型当成页面上什么都没有）。
 * 每次调用都会通知订阅者（dev 探针据此显示回了什么）。
 */
export function readPageState(page?: string): PageStateRead | null {
  const target = page ?? order[order.length - 1]
  let result: PageStateRead | null = null
  if (target !== undefined) {
    const state = readProvider(target)
    if (state !== null) result = { page: target, route: currentRoute(), state }
  }
  const answer: PageStateAnswer = result ?? { page: null, route: currentRoute(), state: null }
  for (const listener of listeners) listener(answer)
  return result
}

/** 订阅「页面被问了一次」（返回取消函数）；只给 dev 探针与测试用。 */
export function subscribePageStateReads(listener: (answer: PageStateAnswer) => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

function readProvider(page: string): Record<string, unknown> | null {
  const set = providers.get(page)
  if (!set || set.size === 0) return null
  // 最后注册的 provider 是该页的当前实例（Set 保持插入序）。
  const provider = [...set].pop()
  if (provider === undefined) return null
  try {
    return provider()
  } catch (error) {
    console.warn(`[ui-snapshot] 页面 ${page} 的状态读取失败：${String(error)}`)
    return null
  }
}
