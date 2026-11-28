/**
 * 技能抽屉开关（跨组件交互态，不穿 props）。
 *
 * 入口在两处——会话侧栏的「技能」按钮与 `/` 菜单的 `manage-skills` 命令——而
 * `Composer` 与 `SessionSidebar` 没有父子关系，所以开关放模块级 Zustand 而非
 * `CopilotState`（后者已很大，抽屉开关与转录/流生命周期无关，不值得进去）。
 */

import { create } from 'zustand'

export const useSkillDrawer = create<{ open: boolean; openDrawer: () => void; closeDrawer: () => void }>((set) => ({
  open: false,
  openDrawer: () => set({ open: true }),
  closeDrawer: () => set({ open: false }),
}))
