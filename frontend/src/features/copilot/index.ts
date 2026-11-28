/**
 * Copilot feature 的对外出口：AppShell / AppNavbar 只从这里引。
 *
 * **openCopilot 例外**：跨 feature 打开面板（携带业务上下文）请引
 * '@/features/copilot/launch'——本文件静态引着 CopilotPanel，从这几
 * re-export 会把整个面板拖进使用方 chunk，破坏懒加载边界。
 */

export { CopilotPanel } from './components/CopilotPanel'

/**
 * AI 助手独立页（/assistant）：与抽屉同一批对话组件、同一个 store，只是把宽度
 * 交给屏幕。与 CopilotPanel 同属 copilot 域 chunk：两者共用 store 与消息组件，
 * 拆成两个 lazy 入口只会把同一份代码拉两次。
 */
export { AssistantPage } from './components/AssistantPage'

/**
 * AI 助手面板的背景压暗遮罩（非模态 dock 只在窄视口下才生效，见组件注释）。
 * 由 AppShell 与面板并列渲染：它不占布局，但需要自己跟面板的挂载/卸载
 * 同步，才能把 fade-out 播完。
 */
export { PanelBackdrop } from './components/PanelBackdrop'

/**
 * 页面自己声明 AI 可操作动作的契约 + 「跳过去之后再继续执行」的消费 hook。
 *
 * 别的 feature 要写 `features/<x>/ui-actions.ts` 时只引这两个符号：
 * - `PageUiAction` 是纯类型（`import type` 编译期擦除，不把本域拖进使用方 chunk）；
 * - `useUiPendingAction` 是运行时 import。跨 feature 只能走本桶出口（ESLint 边界规则），
 *   代价是使用方 chunk 会连带 copilot 域（本文件静态引着 CopilotPanel）；
 *   `launch.ts` 就是为同类「只要一个函数」的需求开过的轻量出口先例。
 */
export type { PageUiAction } from './ui-tools'
export { useUiPendingAction } from './hooks/use-ui-pending-action'

/**
 * 多答裁决的跨 lane 契约（只读）：类型同源于后端 `services/adjudication/contracts.py`。
 * 谁都不许在这里加字段——改契约先改 `docs/04-计划/活跃/adjudication-agent-assignments.md` 附录 A。
 */
export type {
  CriteriaMet,
  CriteriaVerdict,
  EquivalenceCluster,
  FusedHit,
  LaneReview,
  PatchConflict,
  PatchConflictKind,
  Review,
  ReviewStage,
  Synthesis,
  UnscoredReason,
  WritePatchStatus,
} from './adjudication-types'

/**
 * 登出时全局清理 copilot 状态（换账号不得残留上一账号的会话内容）。
 * 动态 import 调用方不必静态依赖本域，保持懒加载边界。
 */
export function resetCopilotState(): Promise<void> {
  return import('./store').then((m) => {
    m.useCopilot.getState().reset()
  })
}
