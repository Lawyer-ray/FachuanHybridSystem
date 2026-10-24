/**
 * Copilot feature 的对外出口：AppShell / AppNavbar 只从这里引。
 *
 * **openCopilot 例外**：跨 feature 打开面板（携带业务上下文）请引
 * '@/features/copilot/launch'——本文件静态引着 CopilotPanel，从这几
 * re-export 会把整个面板拖进使用方 chunk，破坏懒加载边界。
 */

export { CopilotPanel } from './components/CopilotPanel'

/**
 * AI 助手面板的背景压暗遮罩（非模态 dock 只在窄视口下才生效，见组件注释）。
 * 由 AppShell 与面板并列渲染：它不占布局，但需要自己跟面板的挂载/卸载
 * 同步，才能把 fade-out 播完。
 */
export { PanelBackdrop } from './components/PanelBackdrop'

/**
 * 登出时全局清理 copilot 状态（换账号不得残留上一账号的会话内容）。
 * 动态 import 调用方不必静态依赖本域，保持懒加载边界。
 */
export function resetCopilotState(): Promise<void> {
  return import('./store').then((m) => {
    m.useCopilot.getState().reset()
  })
}
