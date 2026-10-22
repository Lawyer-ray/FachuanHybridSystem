/**
 * Copilot feature 的对外出口：AppShell / AppNavbar 只从这里引。
 */

export { CopilotPanel } from './components/CopilotPanel'

/**
 * 登出时全局清理 copilot 状态（换账号不得残留上一账号的会话内容）。
 * 动态 import 调用方不必静态依赖本域，保持懒加载边界。
 */
export function resetCopilotState(): Promise<void> {
  return import('./store').then((m) => {
    m.useCopilot.getState().reset()
  })
}
