/**
 * UI Store
 * UI 状态管理 (Zustand) - 支持持久化
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/**
 * 导航模式
 */
export type NavMode = 'sidebar' | 'topbar'

/**
 * UI 状态接口
 */
interface UIState {
  /** Sidebar 是否收起 */
  sidebarCollapsed: boolean
  /** 导航模式：sidebar（左侧）或 topbar（顶部） */
  navMode: NavMode
  /** 展开的菜单组 */
  expandedGroups: string[]

  // Actions
  /** 切换 Sidebar 收起/展开状态 */
  toggleSidebar: () => void
  /** 设置 Sidebar 收起状态 */
  setSidebarCollapsed: (collapsed: boolean) => void
  /** 设置导航模式 */
  setNavMode: (mode: NavMode) => void
  /** 切换菜单组展开状态 */
  toggleGroup: (groupId: string) => void
  /** 设置展开的菜单组 */
  setExpandedGroups: (groups: string[]) => void
}

/**
 * UI 状态 Store（带持久化）
 */
export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      // 初始状态
      sidebarCollapsed: false,
      navMode: 'sidebar',
      expandedGroups: ['business'], // 默认展开"开始办案"

      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

      setSidebarCollapsed: (collapsed: boolean) =>
        set({ sidebarCollapsed: collapsed }),

      setNavMode: (mode: NavMode) => set({ navMode: mode }),

      toggleGroup: (groupId: string) =>
        set((state) => ({
          expandedGroups: state.expandedGroups.includes(groupId)
            ? state.expandedGroups.filter((id) => id !== groupId)
            : [...state.expandedGroups, groupId],
        })),

      setExpandedGroups: (groups: string[]) =>
        set({ expandedGroups: groups }),
    }),
    {
      name: 'ui-storage',
      partialize: (state) => ({
        sidebarCollapsed: state.sidebarCollapsed,
        navMode: state.navMode,
        expandedGroups: state.expandedGroups,
      }),
    }
  )
)

export const selectSidebarCollapsed = (state: UIState): boolean =>
  state.sidebarCollapsed

export const selectNavMode = (state: UIState): NavMode => state.navMode

export default useUIStore
