/**
 * copilot 的**轻契约面**：页面（别的 feature）只引这一个文件，别引 `ui-tools` 的桶。
 *
 * ## 这个文件承诺什么
 *
 * 「页面要让 AI 能读状态 / 能操作自己」所需要的**全部**东西，不多不少：
 * - 声明与读取页面状态（`registerPageState` / `unregisterPageState` / `readPageState`）；
 * - 当前地址上能调哪些动作名（`availableActionsForPath` + 上限常量）；
 * - 「先跳过去、再由目标页接着做」的队列（`queuePageAction` / `takePageActions`）；
 * - 两个一行接入的 hook（`useUiPageState` / `useUiPendingAction`）；
 * - 页面实现 `features/<x>/ui-actions.ts` 时要用的类型（`PageUiAction` 等）。
 *
 * ## 为什么页面不许引桶（`ui-tools/index.ts`）
 *
 * 桶 → `registry.ts` → `discover.ts`，而 discover 里是
 * `import.meta.glob('/src/features/<feature>/ui-actions.ts', { eager: true })`：
 * 任何页面为了两个 hook 引一次桶，就会把 registry 和整张 eager glob 表拉进**自己的** chunk，
 * discover 再 eager 拉回那个页面所属 feature 的 `ui-actions.ts`——「页面 → copilot/ui-tools
 * → discover → 本 feature」的回头路，构建图里出现环，首要页还要多背一份 copilot 执行层。
 *
 * ## 谁都不许把 registry 相关的东西塞进来
 *
 * 上面那条「零回头路」只靠一件事成立：**本文件不引 registry / discover / store /
 * react-markdown**。往这里加导出之前先问一句「页面真的需要吗」——需要的是页面能力，
 * 不是执行层的内部件；一旦为了少写一行而把桶的符号搬过来，这条边界就当场失效。
 */

export type { PageUiAction, UiActionRequest, UiToolOutcome, UiToolPorts } from './types'

export {
  availableActionsForPath,
  MAX_AVAILABLE_ACTIONS,
  readPageState,
  registerPageState,
  unregisterPageState,
} from './page-state'

export { queuePageAction, takePageActions } from './pending'

export { useUiPageState } from '../hooks/use-ui-page-state'
export { useUiPendingAction } from '../hooks/use-ui-pending-action'
