/**
 * 页面状态注册表 —— AI 问「现在页面上是什么」时，这里给出**结构化小快照**。
 *
 * 页面状态只有页面自己知道（哪个 stage、选了哪条、表单填到哪），所以由页面挂载时主动声明
 * （`hooks/use-ui-page-state.ts`），copilot 只读这张表。
 *
 * **按 provider 集合计数**，不是按页名计「挂载次数」：同一页可能同时挂两个实例（面板 + 助手
 * 页、StrictMode 双跑），按页名计数会让先卸载的那个把还活着的实例一起注销。读状态一律容错
 * （页面代码抛错只 warn 并按「没声明」处理）：一次快照失败只该退回 `no_page_state`。
 *
 * 快照里除了页面声明的 `state`，还带 `availableActions`（这一刻模型还能调哪些动作名）。
 * 那是**动作名字，不是参数结构**：截断只少一条可选项，不会像截结构体那样让模型误以为
 * 「这个字段页面上不存在」——所以这一份可以安全地卡上限。
 */

import { UI_TOOL_SPECS } from './generated'

/**
 * 一次快照最多回多少个动作名。
 *
 * 两端同一口径（后端按同一上限再截一次）：动作名要逐条进模型上下文，而「能做什么」的
 * 价值随条数迅速衰减；只截一次的话，单边放宽就会让每次快照都多背一屏动作名。
 */
export const MAX_AVAILABLE_ACTIONS = 10

/** 页面声明状态的方式：一个读取函数（读到被问那一刻的最新值，而不是注册时的快照）。 */
export type PageStateProvider = () => Record<string, unknown>

/** 一次成功读取：`page` 是页名，`route` 是读出那一刻的真实地址。 */
export type PageStateRead = {
  page: string
  route: string
  state: Record<string, unknown>
  /** 这一刻能调的动作名（本页动作在前、全局动作在后，见 `availableActionsForPath`） */
  availableActions: string[]
}

/** 最近一次被问的结果（`state=null` = 没有任何页面声明状态）。 */
export type PageStateAnswer = {
  page: string | null
  route: string
  state: Record<string, unknown> | null
  availableActions: string[]
}

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
  const route = currentRoute()
  let result: PageStateRead | null = null
  if (target !== undefined) {
    const state = readProvider(target)
    if (state !== null) {
      result = { page: target, route, state, availableActions: availableActionsForPath(route) }
    }
  }
  // 没声明状态时**不给**动作名：页面都没对上，此刻算出来的清单只能算猜，而模型会照着它
  // 去调一个页面根本没实现的动作。后端那条路上同样不带（见 handlers/ui-action-handler.ts）。
  const answer: PageStateAnswer = result ?? { page: null, route, state: null, availableActions: [] }
  for (const listener of listeners) listener(answer)
  return result
}

/**
 * 这个地址上「模型现在就能调」的动作名。
 *
 * **本页动作在前、全局动作在后**，两个理由：
 * - 模型是顺序读清单的；
 * - 截断丢的是**尾部**，而尾部先轮到的只会是全局动作（`ui_navigate` / `ui_copilot_open`）
 *   ——不会出现「这一页的专属动作被截掉了、只剩两条通用动作」这种最坏的截法。
 *
 * 只回名字不回参数结构：结构由后端清单的 `args_schema` 管，前端再抄一份就是两处真相。
 */
export function availableActionsForPath(pathname: string): string[] {
  const path = stripQuery(pathname)
  const names: string[] = []
  // 两轮而不是一轮分桶：本页动作整体排在全局动作之前，读起来就是最终顺序
  for (const spec of UI_TOOL_SPECS) {
    if (spec.route !== null && isUnderRoute(path, spec.route)) names.push(spec.name)
  }
  for (const spec of UI_TOOL_SPECS) {
    if (spec.route === null) names.push(spec.name)
  }
  // 生成物里同名动作目前只有一条，但「唯一」是生成器的事；本函数不押注它（重复名会让模型
  // 把同一个动作看两遍，还白占截断名额）
  return [...new Set(names)].slice(0, MAX_AVAILABLE_ACTIONS)
}

/** 只留 pathname：`?stage=todo` 之类是页面自己的状态，不参与「在哪一页」的判断。 */
function stripQuery(path: string): string {
  const queryAt = path.indexOf('?')
  return queryAt === -1 ? path : path.slice(0, queryAt)
}

/**
 * 这个地址是否落在 `route` 那一页上（query 已剥掉；子路径也算，如 `/material-prep/393`）。
 *
 * 必须按**段**比：`/material-prep-x` 不是 `/material-prep` 的子页，裸 `startsWith` 会把它的
 * 动作算给 `/material-prep`。这条判据与 `registry.ts` 的 `isUnderRoute` 是同一条，刻意各写
 * 一份：registry 会把 `discover.ts` 的 eager glob 拖进来，而本文件要能被页面侧的轻契约面
 * （`contract.ts`）直接引——回头路就是这样长出来的。两处的 `/material-prep-x` 用例各自钉死。
 */
function isUnderRoute(path: string, route: string): boolean {
  if (route === '/') return path === '/'
  return path === route || path.startsWith(`${route}/`)
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
