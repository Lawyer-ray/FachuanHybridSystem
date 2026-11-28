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
 *
 * 另有一份 `blockedActions`：「这一页**有**、但**此刻**做不了」的动作 + 一句原因。
 * `availableActions` 是按路由静态算的（清单里这一页有什么），不知道「选中了哪一条」，
 * 所以两者**不互斥**；同一条两边都在时以 `blockedActions` 为准（理由：前置没满足）。
 * 没有它，模型分不清「页面没实现」与「有但此刻不可用」，会自己编一个 `packId` 硬调。
 *
 * 快照分**两半**：`state` 进模型上下文，`privateState`（后端 `private_state`）**绝不进**。
 * 页面用它放不该给模型看的东西——律师还没提交的草稿、原始主键 id、排查用的调试字段。
 * 分开的理由很务实：只有一条通道时，页面总有理由把「先塞进去再说」的东西也塞进 `state`，
 * 而模型会把草稿当既成事实转述给律师。`privateState` 只进日志（键名 + 字节数，不打值；
 * 上限 4000 字，比 `state` 宽一倍，超限后端直接拒）。
 */

import { UI_TOOL_SPECS } from './generated'

/**
 * 一次快照最多回多少个动作名。
 *
 * 两端同一口径（后端按同一上限再截一次）：动作名要逐条进模型上下文，而「能做什么」的
 * 价值随条数迅速衰减；只截一次的话，单边放宽就会让每次快照都多背一屏动作名。
 */
export const MAX_AVAILABLE_ACTIONS = 10

/**
 * 一次快照最多回多少条「做不了 + 为什么」。
 *
 * 与 `MAX_AVAILABLE_ACTIONS` 同一理由与同一数值（后端 `UiSnapshotIn` 按同一上限再截一次）：
 * 每条都要进模型上下文，而好消息是「做不了」的条目天然很少——超过 10 条就说明这份清单
 * 已经不是「这一刻的阻塞」，而是页面在抄整张能力表。
 */
export const MAX_BLOCKED_ACTIONS = 10

/** 「这一页有、但此刻做不了」的一条：动作名必须在后端清单里，原因是给模型看的一句话。 */
export interface BlockedAction {
  /** 动作名（必须在后端清单里） */
  name: string
  /** 给模型看的一句原因（≤ 200 字） */
  reason: string
}

/** 页面声明状态的方式：一个读取函数（读到被问那一刻的最新值，而不是注册时的快照）。 */
export type PageStateProvider = () => Record<string, unknown>

/** 一次成功读取：`page` 是页名，`route` 是读出那一刻的真实地址。 */
export type PageStateRead = {
  page: string
  route: string
  state: Record<string, unknown>
  /** 这一刻能调的动作名（本页动作在前、全局动作在后，见 `availableActionsForPath`） */
  availableActions: string[]
  /** 有、但此刻做不了的动作与原因（截 10 条；空表 = 本页没报） */
  blockedActions: BlockedAction[]
  /** 不进模型上下文的那一半（未提交草稿 / 原始 id / 调试字段）；空对象 = 本页没报 */
  privateState: Record<string, unknown>
}

/** 最近一次被问的结果（`state=null` = 没有任何页面声明状态）。 */
export type PageStateAnswer = {
  page: string | null
  route: string
  state: Record<string, unknown> | null
  availableActions: string[]
  blockedActions: BlockedAction[]
  privateState: Record<string, unknown>
}

/** 页名 → 已挂载的 provider（Set 保持插入序，最后一个 = 当前实例）；`order` 记注册顺序。 */
const providers = new Map<string, Set<PageStateProvider>>()
const order: string[] = []
const listeners = new Set<(answer: PageStateAnswer) => void>()

/**
 * 页名 → 「这一页有、但此刻做不了」的动作。**与 `providers` 分开存**：供应商那边是
 * 「状态怎么读」，这是一份由页面（`hooks/use-ui-page-state.ts`）推进来的静态快照。
 *
 * 多实例（面板 + 助手页同时挂同一页）是**后写者胜**，本表不承诺合并语义：`blockedActions`
 * 是「这一刻」的事实，两个实例看到的选择本来就可能不同，合并只会造出一份谁都没见过的清单。
 */
const blockedByPage = new Map<string, BlockedAction[]>()

/**
 * 页名 → 「**不给模型看**的那一半」状态（未提交草稿 / 原始主键 id / 调试字段）。
 *
 * 与 `blockedByPage` 同款写法（模块级 Map + 页面推 + 卸载清），**不另立一套机制**：两半走同一条
 * 上行通道（`handlers/ui-action-handler.ts` 一次应答带上两半），只是后端把它们分到模型上下文
 * 与日志两个去处。多实例同样是后写者胜——它是「这一刻」的事实，合并只会造出谁都没见过的快照。
 */
const privateByPage = new Map<string, Record<string, unknown>>()

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

/**
 * 页面上报「此刻做不了什么」（由 `useUiPageState` 每次渲染推进来；不对外承诺多实例语义）。
 *
 * 截断在**写入**时就做掉：读的时候再截等于让内存里常驻一张没人会看的超长表。
 */
export function setPageBlockedActions(page: string, list: BlockedAction[]): void {
  blockedByPage.set(page, list.slice(0, MAX_BLOCKED_ACTIONS))
}

/** 页面卸载 / 重新挂载时清掉这条登记（旧原因留着 = 让模型对着不存在的页面下结论）。 */
export function clearPageBlockedActions(page: string): void {
  blockedByPage.delete(page)
}

/**
 * 页面上报「不进模型上下文」的那一半（由 `useUiPageState` 每次渲染推过来）。
 *
 * 不做合并：后写者胜（同 `setPageBlockedActions`）。它**不保证**与 `state` 同一次提交——
 * 所以页面别把这里当唯一真相，它只是「不想给模型看，但希望出问题时能查到」的落脚点。
 */
export function setPagePrivateState(page: string, value: Record<string, unknown>): void {
  privateByPage.set(page, value)
}

/** 页面卸载 / 重新挂载时清掉：上一个实例的私有状态属于上一个实例，留着就是假事实。 */
export function clearPagePrivateState(page: string): void {
  privateByPage.delete(page)
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
      result = {
        page: target,
        route,
        state,
        availableActions: availableActionsForPath(route),
        blockedActions: (blockedByPage.get(target) ?? []).slice(0, MAX_BLOCKED_ACTIONS),
        privateState: privateByPage.get(target) ?? {},
      }
    }
  }
  // 没声明状态时**不给**动作名（含「做不了」那份）：页面都没对上，此刻算出来的清单只能算猜，
  // 而模型会照着它去调一个页面根本没实现的动作。后端那条路上同样不带
  // （见 handlers/ui-action-handler.ts）。
  const answer: PageStateAnswer = result ?? {
    page: null,
    route,
    state: null,
    availableActions: [],
    blockedActions: [],
    privateState: {},
  }
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
