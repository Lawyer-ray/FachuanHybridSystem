/**
 * UI Store
 * UI 状态管理 (Zustand) - 支持持久化
 */

import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface UIState {
  sidebarCollapsed: boolean
  expandedGroups: string[]

  toggleSidebar: () => void
  setSidebarCollapsed: (collapsed: boolean) => void
  toggleGroup: (groupId: string) => void
  setExpandedGroups: (groups: string[]) => void
}

export const useUIStore = create<UIState>()(
  persist(
    (set) => ({
      sidebarCollapsed: false,
      expandedGroups: ['business'],

      toggleSidebar: () =>
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed })),

      setSidebarCollapsed: (collapsed: boolean) =>
        set({ sidebarCollapsed: collapsed }),

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
        expandedGroups: state.expandedGroups,
      }),
    }
  )
)

export const selectSidebarCollapsed = (state: UIState): boolean =>
  state.sidebarCollapsed

export default useUIStore
