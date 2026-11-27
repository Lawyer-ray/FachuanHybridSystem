/**
 * UI 动作执行层的端口与结果类型 —— 「执行器需要什么浏览器能力」的唯一契约。
 *
 * **为什么执行器不直接 import router / sonner / launch**：ui-tools 是纯逻辑层，
 * 真正持有 navigate / toast 的是组件树（`main.tsx` 是声明式 BrowserRouter，React
 * 之外拿不到 router）。把能力做成端口注入，执行器才能在 node 环境直接单测
 * （`*.node.test.ts`），也才不会把 React、store 拖进一个本该零依赖的目录。
 *
 * **本文件零运行时依赖**（只有 `import type`）：任何真实 import 都会让上面的
 * 单测把整条 React 依赖链拉进进程。
 */

// 端口里的业务上下文直接复用 launch.ts 的那个类型，而不是再抄一遍
// `{ origin; refId; title }`：同一件事两处拼写，字段一改就静默少传一个。
// `import type` 编译期擦除，不破坏本文件的零运行时依赖。
import type { CopilotLaunchContext } from '../launch'
// `export type { … } from` 不会把名字带进本文件作用域，`PageUiAction` 还要用它，故单列一次 import
import type { UiToolName } from './generated'

/**
 * 动作名的权威定义在生成物里，这里只做转出：调用方（hooks / store / 组件）
 * 引 `ui-tools` 就够了，不必知道哪个符号来自哪个文件。
 */
export type { UiToolName } from './generated'

/** 执行器能用的浏览器能力（真实实现由 `hooks/use-ui-tool-host` 注入） */
export interface UiToolPorts {
  navigate: (to: string, opts?: { replace?: boolean }) => void
  /**
   * 当前地址（pathname + search）。
   * `ui_material_prep_set_stage` 用它保住 `?message=` 深链接——直接跳
   * `/material-prep?stage=todo` 会把「打开某条消息」的直达能力抹掉
   * （`use-desk-filters.ts` 的 setStage 正是为此在现有参数上改，而不是整体替换）。
   */
  currentPath: () => string
  toast: (message: string) => void
  /** 跨 feature「让目标页面自己动一下」的 window 事件（`launch.ts` 的既定模式） */
  dispatch: (event: string, detail?: unknown) => void
  /** 打开助手面板；不传上下文 = 普通打开（`features/copilot/launch.ts` 的 openCopilot） */
  openCopilot: (ctx?: CopilotLaunchContext) => void
}

/**
 * 失败分类。每个码都对应一个**不同的处置**，不是同一种错误的不同说法：
 * - `unknown_action`：前后端版本漂移（先发前端、再发后端才安全），要打点告警；
 * - `invalid_args`：模型给的参数不合法，可以在下轮改参数重试；
 * - `route_unreachable`：路径不在白名单里（安全拦截），**不许**重试同样参数；
 * - `aborted`：律师点了「停下」，同 run 后续动作一律忽略；
 * - `executor_error`：执行器自己抛了异常（代码 bug），必须落 banner 红态。
 */
export type UiToolErrorCode =
  | 'unknown_action'
  | 'invalid_args'
  | 'route_unreachable'
  | 'aborted'
  | 'executor_error'

/** 一次动作执行的结果；失败必带码与给律师看的中文说明 */
export type UiToolOutcome = { ok: true; detail?: string } | { ok: false; code: UiToolErrorCode; message: string }

/**
 * 事件 → store 的入参。`action` 是 `string` 而不是 `UiToolName`：
 * 未知动作必须能流到这里被判成 `unknown_action`，窄化成闭集联合就等于把
 * 「后端新增了动作、前端还没发版」这种唯一需要告警的场景从类型上抹掉。
 */
export interface UiActionRequest {
  callId: string
  action: string
  args: Record<string, unknown>
  /** 后端声明的期望路由前缀；`null` = 任意页面 */
  route: string | null
}

/** 一条动作的执行器：已校验过的参数 → 一次浏览器动作 */
export type UiExecutor = (
  args: Record<string, unknown>,
  ports: UiToolPorts,
) => UiToolOutcome | Promise<UiToolOutcome>

/**
 * 页面自己声明的动作实现：约定文件 `features/<feature>/ui-actions.ts` 的
 * `uiActions` 数组元素（聚合逻辑见 `ui-tools/discover.ts`）。
 *
 * **为什么 `action` 是 `UiToolName` 而不是 `string`**：动作名的唯一来源是后端清单
 * （`generated.ts` 由 `manifest.py` 反射生成）。写成 string 时，页面可以「实现」一个
 * 模型永远不会调用的名字，而这件事既不红也不报错——`discover.ts` 的收集期还会再拦
 * 一次（防陈旧生成物），但类型这一层更便宜。
 *
 * **为什么 `execute` 直接用 `UiExecutor` 而不是再抄一遍函数类型**：两处手抄之后，
 * 页面实现会以「参数少一个 / 返回值形状不同」的形式静默错位，而这正是闭集守卫
 * （`Record<UiToolName, UiExecutor>`）当初要消灭的故障形态。
 */
export interface PageUiAction {
  action: UiToolName
  execute: UiExecutor
}
