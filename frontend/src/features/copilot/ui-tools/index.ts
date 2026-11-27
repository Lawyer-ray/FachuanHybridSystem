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

export type { UiActionRequest, UiExecutor, UiToolErrorCode, UiToolOutcome, UiToolPorts } from './types'

export { resolveExecutor, resolveSpec, runUiTool, UI_EXECUTORS, UI_TOOL_NAMES, validateArgs } from './registry'

export type { MaterialPrepStage } from './routes'
export {
  isMaterialPrepStage,
  MATERIAL_PREP_STAGES,
  pathForMaterialPrepStage,
  pathForNavigate,
} from './routes'
