/**
 * 动作名 → 执行器：前端执行层的**闭集**，以及参数的**第二道**守卫。
 *
 * 两道闸都是「静默失效」的解药：
 * 1. **名字闭集**：`UiToolName` 只来自后端清单（`generated.ts`），表里写一个清单外的名字
 *    编译就红——「前端实现了模型永远不会调的动作」是假能力，不是能力。
 *    闭集的另一半「清单里有、执行器没有」现在由**运行期**门禁守（为什么不在编译期了、
 *    门禁搬去了哪两条用例，见 `UI_EXECUTORS` 的 docstring）。
 * 2. 后端已按 `args_schema` 校验过一轮，这里再校验一次：灰度期前端旧、后端新时，
 *    新参数形状会带着旧前端一起跑，此时唯一能拦住的是本地守卫。
 *
 * **不写业务 API 调用**：`confirm` 类动作要真写库时，走 `ports.dispatch` 让目标
 * feature 自己消费（`launch.ts` 的既定模式），执行器不 import 别的 feature 内部——
 * 那会把对方的 chunk 拖进 copilot 的懒加载边界。
 *
 * 页面自己声明的执行器（`features/<x>/ui-actions.ts`，收集见 `discover.ts`）在这里**优先于**
 * 内置表：新增页面只写那个约定文件，不用回来改本文件。代价是「执行器里可以没有安全检查」，
 * 所以路径白名单被上提到了 `runUiTool` 层、与实现无关（见那里的注释）。
 */

import { COLLECTED_PAGE_EXECUTORS, resolveDiscoveredExecutor, setDiscoveredExecutors } from './discover'
import { UI_TOOL_BY_NAME, UI_TOOL_SPECS } from './generated'
import type { UiToolName, UiToolSpec } from './generated'
import { queuePageAction } from './pending'
import { MATERIAL_PREP_STAGES, pathForMaterialPrepStage, pathForNavigate } from './routes'
import type { UiActionRequest, UiExecutor, UiToolOutcome, UiToolPorts } from './types'

/** JSON 对象判定（数组与 null 都不算对象；与后端 schema.py 的口径一致） */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

/**
 * 只校验 `type` / `enum` / `required` / `additionalProperties` —— 与后端
 * `apps/agent/services/ui_action/schema.py` 支持的关键字**逐个对齐**。
 *
 * 多支持一个关键字就多一个漂移点：清单里写了 `pattern` 而这里不认，结果就是
 * 「看起来校验过了」的静默放行，比不校验更危险。要扩就先扩两端。
 */
const TYPE_CHECKS: Record<string, (value: unknown) => boolean> = {
  string: (value) => typeof value === 'string',
  // 布尔值不是数字：不显式挡，`{"stage": true}` 之类会混过 integer/number
  integer: (value) => typeof value === 'number' && Number.isInteger(value),
  number: (value) => typeof value === 'number' && Number.isFinite(value),
  boolean: (value) => typeof value === 'boolean',
  object: isRecord,
  array: Array.isArray,
}

/** 参数是否符合该动作的 schema（`true` = 放行） */
export function validateArgs(spec: UiToolSpec, args: unknown): boolean {
  if (!isRecord(args)) return false
  const schema = spec.argsSchema
  const properties = isRecord(schema.properties) ? schema.properties : {}
  if (schema.additionalProperties === false) {
    for (const key of Object.keys(args)) {
      // 多余参数一律拒：模型自己编出来的字段要么是误解，要么该是另一个动作的参数
      if (!Object.hasOwn(properties, key)) return false
    }
  }
  if (Array.isArray(schema.required)) {
    for (const name of schema.required) {
      if (typeof name === 'string' && !Object.hasOwn(args, name)) return false
    }
  }
  for (const [name, value] of Object.entries(args)) {
    const property = properties[name]
    if (!isRecord(property)) continue
    const check = typeof property.type === 'string' ? TYPE_CHECKS[property.type] : undefined
    if (check && !check(value)) return false
    const allowed = property.enum
    if (Array.isArray(allowed) && !allowed.includes(value)) return false
  }
  return true
}

/** 名字 → 规格；清单里没有的名字返回 `null`（不是抛异常：版本漂移要能被分类） */
export function resolveSpec(name: string): UiToolSpec | null {
  return Object.hasOwn(UI_TOOL_BY_NAME, name) ? UI_TOOL_BY_NAME[name as UiToolName] : null
}

/**
 * 名字 → 执行器。**顺序：页面声明优先，内置兜底；名字不在清单里返回 `null`。**
 *
 * 为什么页面优先：动作实现终将要搬回各自 feature（`features/<x>/ui-actions.ts`），
 * 迁移期两边并存时页面那份才是最新的；内置优先会让「搬走之后的行为改动」静默失效。
 *
 * 覆盖内置执行器的安全代价由两层挡住，都不在执行器内部：
 * 1. 闭集不变——名字必须在后端清单（`generated.ts`）里，发现期就已过滤；
 * 2. `runUiTool` 的白名单守卫在**执行器之外**：`ui_navigate` 无论谁实现，都先过
 *    `pathForNavigate`。所以这里可以允许覆盖，但不许**悄悄**覆盖。
 */
export function resolveExecutor(name: string): UiExecutor | null {
  const fromPage = resolveDiscoveredExecutor(name)
  if (fromPage) return fromPage
  // `hasOwn` 不能省：内置表是普通对象，`resolveExecutor('toString')` 会摸到原型链上的函数
  if (!Object.hasOwn(UI_EXECUTORS, name)) return null
  return UI_EXECUTORS[name as UiToolName] ?? null
}

/**
 * 换上「页面声明的执行器表」，并把「覆盖了内置执行器」在**收集期**吵一句。
 *
 * 生产路径只有一个调用点（本文件末尾的模块初始化）；导出是为了让测试注入假模块——
 * 内置表只覆盖 3 条通用动作，页面声明那条通道（`ui_material_prep_judge`）要靠注入
 * 才能证明「页面优先」真的生效。
 */
export function setPageExecutors(next: ReadonlyMap<string, UiExecutor>): void {
  setDiscoveredExecutors(next)
  for (const name of next.keys()) {
    if (!Object.hasOwn(UI_EXECUTORS, name)) continue
    console.warn(
      `页面实现覆盖了内置执行器 ${name}；若是 ui_navigate 请确认白名单守卫仍在（现在它在 runUiTool 层，不受覆盖影响）`,
    )
  }
}

/**
 * `ui_copilot_open` 的业务上下文：三个字段齐全才认。
 *
 * 缺一个就退回「普通打开」而不是报错：打开面板本身是律师要的那件事，
 * 少个 chip 只是少了上下文；反过来硬拼一个 `{origin:'case', refId:0, title:''}`
 * 会让面板头挂上一条根本不存在的案件——比不挂更糟。
 */
function copilotContext(args: Record<string, unknown>): { origin: 'case' | 'contract'; refId: number; title: string } | null {
  const { origin, refId, title } = args
  if ((origin !== 'case' && origin !== 'contract') || typeof refId !== 'number' || typeof title !== 'string') {
    return null
  }
  return { origin, refId, title }
}

/** 报错文案里的阶段清单：从 routes 的常量拼，不另抄一份字面量 */
const MATERIAL_PREP_STAGE_LIST = MATERIAL_PREP_STAGES.join(' / ')

/**
 * 白名单拒绝的统一文案：内置执行器与 `runUiTool` 的通用守卫共用一句。
 * 各写一份的那天，同一件事在 banner 上会变成两种说法。
 */
const NAVIGATE_DENIED_MESSAGE = '跳转被拒：这个地址不在站内白名单里（只接受应用自己的页面路径）'

/**
 * 当前地址是否已经落在目标页上（`/material-prep?stage=todo` 算在 `/material-prep` 上，
 * 子路径 `/material-prep/393` 也算——它与列表页共用同一个组件）。
 *
 * 必须按**段**比：`/material-prep-x` 不是 `/material-prep` 的子页面，用裸 `startsWith`
 * 会把「排队 + 跳过去」误判成「已经在了」，动作就落在错页上。
 */
function isUnderRoute(currentPath: string, route: string): boolean {
  const queryAt = currentPath.indexOf('?')
  const pathname = queryAt === -1 ? currentPath : currentPath.slice(0, queryAt)
  if (route === '/') return pathname === '/'
  return pathname === route || pathname.startsWith(`${route}/`)
}

/**
 * 内置执行器表：只有「URL 直达、不依赖任何 feature 内部状态」的通用动作住在这里。
 *
 * ## 为什么类型是 `Partial<Record<…>>` 而不是 `Record<…>`
 *
 * `Record<UiToolName, UiExecutor>` 的语义是「**每个**清单动作都必须在这张表里有实现」。
 * material-prep 接入后这条不成立了：`ui_material_prep_judge` 要真写库，实现归页面自己
 * （`features/material-prep/ui-actions.ts`，由 `discover.ts` 的 glob 收集）。硬塞进这里
 * 等于让 copilot 的执行层 import 材料预处理页的 API 模块，把两边的 chunk 绑在一起。
 *
 * **放宽的是「完备性在编译期保证」，不是闭集**：键仍然是 `UiToolName`（清单外的名字编译
 * 就红），`runUiTool` 仍先查 `resolveSpec`，未知名字照旧判 `unknown_action`。
 *
 * ## 完备性门禁搬到了运行期，两条缺一不可
 *
 * 1. `registry.node.test.ts`「清单里的每条动作都能 resolve 到执行器」：逐条
 *    `resolveExecutor(spec.name)` 非空——它同时覆盖本表与页面声明表，是离原来那条
 *    编译期保证最近的东西；
 * 2. `discover.node.test.ts`「真实聚合」：证明 glob 真的收得到 material-prep 的实现。
 *    只有第 1 条时，glob 模式写错也只会红在「缺执行器」，查半天才知道红在哪一层。
 *
 * 所以「缺实现」的故障形态仍然是**红**（测试红，且 CI 必跑），不是静默——这次放宽
 * 没有削弱守卫，只是把守卫从编译器挪到了会指名道姓的那条用例上。
 */
export const UI_EXECUTORS: Partial<Record<UiToolName, UiExecutor>> = {
  ui_navigate: (args, ports) => {
    const path = pathForNavigate(args.path)
    if (path === null) {
      return { ok: false, code: 'route_unreachable', message: NAVIGATE_DENIED_MESSAGE }
    }
    ports.navigate(path)
    return { ok: true, detail: path }
  },
  ui_copilot_open: (args, ports) => {
    const context = copilotContext(args)
    ports.openCopilot(context ?? undefined)
    return { ok: true, detail: context ? `已在「${context.title}」上下文中打开助手` : '已打开助手' }
  },
  ui_material_prep_set_stage: (args, ports) => {
    const path = pathForMaterialPrepStage(args.stage, ports.currentPath())
    if (path === null) {
      // 走到这里说明 validateArgs 放过了非法 stage（schema 与本文件不同源）——按参数错误报
      return {
        ok: false,
        code: 'invalid_args',
        message: `切换阶段被拒：stage 只能是 ${MATERIAL_PREP_STAGE_LIST}，收到 ${String(args.stage)}`,
      }
    }
    // replace：切筛选是原地改状态，压进历史栈会让「后退」一步步退回上一个筛选
    ports.navigate(path, { replace: true })
    return { ok: true, detail: path }
  },
}

/**
 * 一次完整的动作执行：解析 → 校验 → 执行 → 兜异常。
 *
 * 放在这里而不是 store：错误码的分类是**执行层知识**（哪个码能重试、哪个码要告警），
 * 而 store 只该管幂等、打断与落态。把分类留在 registry，store 的 `runUiAction`
 * 就只剩「取结果、写 uiToolRuns」两件事。
 */
export async function runUiTool(req: UiActionRequest, ports: UiToolPorts): Promise<UiToolOutcome> {
  const executor = resolveExecutor(req.action)
  const spec = resolveSpec(req.action)
  if (!executor || !spec) {
    // 先发前端、再发后端是灰度铁律；命中这里说明顺序反了，要打点告警而不是猜着执行
    return { ok: false, code: 'unknown_action', message: `前端不认识动作 ${req.action}（前端版本落后于后端）` }
  }
  if (!validateArgs(spec, req.args)) {
    return { ok: false, code: 'invalid_args', message: `动作 ${req.action} 的参数不合法` }
  }
  // 与实现无关的安全守卫：路径白名单**不跟着执行器走**。页面可以在 `ui-actions.ts` 里
  // 覆盖 ui_navigate 的实现（见 resolveExecutor），但绕不过这一行——否则「谁能覆盖
  // 执行器」就等于「谁能放开跳转白名单」，而白名单是整条链路上唯一的安全边界。
  if (req.action === 'ui_navigate' && pathForNavigate(req.args.path) === null) {
    return { ok: false, code: 'route_unreachable', message: NAVIGATE_DENIED_MESSAGE }
  }
  // 动作落在**还没挂载**的页面上：先排队再跳，由目标页挂载时取走（hooks/use-ui-pending-action）。
  // 只对页面自己声明的执行器生效：内置三条本来就是 URL 直达（切阶段用 replace 原地改
  // query、并要保住当前页的 ?message=），排到目标页再跑会多跳一次，还丢深链接。
  if (
    spec.route !== null &&
    resolveDiscoveredExecutor(req.action) !== null &&
    !isUnderRoute(ports.currentPath(), spec.route)
  ) {
    queuePageAction(spec.route, req)
    ports.navigate(spec.route)
    return { ok: true, detail: `已跳转到 ${spec.route}，页面就绪后继续` }
  }
  try {
    return await executor(req.args, ports)
  } catch (error) {
    return {
      ok: false,
      code: 'executor_error',
      message: error instanceof Error ? error.message : String(error),
    }
  }
}

/** 清单里的动作名（测试与治理门禁用；顺序即清单声明序） */
export const UI_TOOL_NAMES: readonly UiToolName[] = UI_TOOL_SPECS.map((spec) => spec.name)

// 模块加载即装上 glob 收集到的页面动作表（收集期提示，不等到第一次动作才吵）。
// 必须放在 `UI_EXECUTORS` 定义之后：`setPageExecutors` 要读它判断「覆盖了内置」。
setPageExecutors(COLLECTED_PAGE_EXECUTORS)
