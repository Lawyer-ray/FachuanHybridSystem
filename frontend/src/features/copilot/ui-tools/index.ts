/**
 * `ui-tools` 的桶出口：执行层对外的唯一引用面（hooks / store / 组件都从这里引）。
 *
 * 为什么要桶：接线方（`hooks/use-ui-tool-host`、`store/ui-tools`、`handlers/ui-action-handler`）
 * 若各自深引 `./generated` / `./registry` / `./routes`，文件名一改就是三处静默断链；
 * 桶出口让「执行层能对外提供什么」只有一张清单。
 *
 * 注意这里不导出任何会碰 React / store 的东西：ui-tools 是纯逻辑层，
 * 才能被 node 环境的单测直接加载。
 */

export type { UiToolName, UiToolRisk, UiToolSpec, UiToolTier, UiToolUndo } from './generated'
export { UI_TOOL_BY_NAME, UI_TOOL_SPECS } from './generated'

export type {
  PageUiAction,
  UiActionOutcome,
  UiActionRequest,
  // 结算回执的线上契约（`POST /agent/ui-action-results`）：只有类型，不带运行时依赖
  UiActionResultAck,
  UiActionResultReceipt,
  UiActionResultSettlement,
  UiExecutor,
  UiToolErrorCode,
  UiToolOutcome,
  UiToolPorts,
} from './types'

// 「等目标页面挂载后再执行」的队列：入队由 registry 在做（页面没挂载时），
// 出队由 hooks/use-ui-pending-action 做。两个方向都从这里取，路径只拼一次。
export { MAX_PENDING_PAGE_ACTIONS, queuePageAction, takePageActions } from './pending'

export { resolveExecutor, resolveSpec, runUiTool, UI_EXECUTORS, UI_TOOL_NAMES, validateArgs } from './registry'

export type { MaterialPrepStage } from './routes'
export {
  isMaterialPrepStage,
  MATERIAL_PREP_STAGES,
  pathForMaterialPrepStage,
  pathForNavigate,
} from './routes'
