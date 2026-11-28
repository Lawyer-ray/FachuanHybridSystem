/**
 * 页面动作的自动发现：`features/<feature>/ui-actions.ts` → 执行器表。
 *
 * ## 为什么要有这一层
 *
 * 之前页面内动作全部硬编码在 `registry.ts` 的 `UI_EXECUTORS` 里：新增一个页面后，
 * AI 只能「打开」它、不能操作它，而且要改 central 注册表才知道它有哪些动作。改成
 * 「feature 自己在 `ui-actions.ts` 里声明实现，这里用 `import.meta.glob` 聚合」后，
 * 新增页面只写 1 个文件，不用碰 copilot 域的代码。
 *
 * ## 为什么必须 eager
 *
 * 执行器要在一次动作用同步可用：懒加载会让**第一次**动作多等一个 chunk，而 UI 动作
 * 是毫秒级的「改个地址」，等 chunk 的那一刻表现为「AI 说了要跳，页面先愣一下」。
 *
 * ## 闭集语义不变（这是与「省掉注册表」并列的另一半）
 *
 * 模型只认识**后端 `manifest.py` 声明过的工具**。所以发现表里出现**清单外**的动作名时，
 * 收集期 warn 一句并**不**让它可执行：前端单方面实现一个动作，模型永远不会调用它，
 * 放行只会让 `unknown_action` 守卫形同虚设（那是灰度期唯一能识别版本漂移的地方）。
 */

import { UI_TOOL_BY_NAME } from './generated'
import type { PageUiAction, UiExecutor } from './types'

/** 约定文件的模块形状：只认具名导出 `uiActions`（模板见 `docs/harness/frontend/ui-actions.md`） */
export interface UiActionModule {
  uiActions?: readonly PageUiAction[]
}

/** 提醒通道：默认 console.warn；测试注入 spy 以钉死文案 */
export type Warn = (message: string) => void

const warnToConsole: Warn = (message) => {
  console.warn(message)
}

/**
 * 约定文件里 `uiActions` 的运行时形状判定。
 *
 * 用自定义谓词而不是直接 `Array.isArray`：后者的类型谓词是 `any[]`，元素被推成 any 之后
 * 字段写错（`entry.actoin`）要等运行期才发现。
 */
function isPageActionList(value: unknown): value is readonly PageUiAction[] {
  return Array.isArray(value)
}

/**
 * 模块表 → 执行器表（纯逻辑，测试直接喂假模块）。
 *
 * 三个分支都要出声或静默跳过，且**都不抛异常**：一个 feature 的文件写错不该让整个
 * 执行层加载失败（那时所有动作一起失效，比少一个动作糟得多）。
 * - 动作名不在清单里 → warn「模型不会调用它」并跳过（闭集）；
 * - 模块没导出 `uiActions` 数组 → warn 并跳过（约定文件存在但形状错）；
 * - 合法 → 进表。
 */
export function collectExecutors(
  modules: Record<string, UiActionModule>,
  warn: Warn = warnToConsole,
): Map<string, UiExecutor> {
  const executors = new Map<string, UiExecutor>()
  for (const [path, module] of Object.entries(modules)) {
    const declared: unknown = module.uiActions
    if (!isPageActionList(declared)) {
      warn(`${path} 没有导出 uiActions 数组，已跳过（约定见 docs/harness/frontend/ui-actions.md）`)
      continue
    }
    for (const entry of declared) {
      if (!Object.hasOwn(UI_TOOL_BY_NAME, entry.action)) {
        warn(`动作 ${entry.action} 已在前端实现，但后端 manifest 没声明 → 模型不会调用它（${path}）`)
        continue
      }
      executors.set(entry.action, entry.execute)
    }
  }
  return executors
}

/** glob 收集出的真实执行器表（测试注入假表后用它还原） */
export const COLLECTED_PAGE_EXECUTORS: ReadonlyMap<string, UiExecutor> = collectExecutors(
  import.meta.glob<UiActionModule>('/src/features/*/ui-actions.ts', { eager: true }),
)

/** 当前生效的发现表（生产路径唯一的写入点是 registry 的模块初始化，见下方 setDiscoveredExecutors） */
let discoveredExecutors: ReadonlyMap<string, UiExecutor> = COLLECTED_PAGE_EXECUTORS

/**
 * 替换发现表。生产只有一个调用点（`registry.setPageExecutors`）；测试也走那个口子——
 * 它顺带检查「是否覆盖了内置执行器」，直接调本函数会漏掉那条提示。
 */
export function setDiscoveredExecutors(next: ReadonlyMap<string, UiExecutor>): void {
  discoveredExecutors = next
}

/** 名字 → 页面声明的执行器；没有则 `null`（调用方据此决定「内置兜底」还是「排队等页面」） */
export function resolveDiscoveredExecutor(name: string): UiExecutor | null {
  return discoveredExecutors.get(name) ?? null
}
