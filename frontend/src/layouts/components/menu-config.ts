/**
 * 菜单配置
 * 统一管理侧边栏和顶部导航的菜单结构
 */

import {
  LayoutDashboard,
  Briefcase,
  FileText,
  Users,
  Zap,
  Shield,
  FileSearch,
  Settings,
  User,
  Cog,
  type LucideIcon,
} from 'lucide-react'
import { PATHS } from '@/routes/paths'

/**
 * 菜单项
 */
export interface MenuItem {
  id: string
  icon: LucideIcon
  label: string
  path: string
  badge?: number
}

/**
 * 菜单组
 */
export interface MenuGroup {
  id: string
  label: string
  icon?: LucideIcon
  items: MenuItem[]
}

/**
 * 顶级菜单项（无子菜单）
 */
export interface TopLevelMenuItem {
  id: string
  icon: LucideIcon
  label: string
  path: string
  badge?: number
}

/**
 * 菜单配置类型
 */
export type MenuConfig = (TopLevelMenuItem | MenuGroup)[]

/**
 * 判断是否为菜单组
 */
export function isMenuGroup(item: TopLevelMenuItem | MenuGroup): item is MenuGroup {
  return 'items' in item
}

/**
 * 菜单配置
 */
export const menuConfig: MenuConfig = [
  // 仪表盘 - 顶级菜单
  {
    id: 'dashboard',
    icon: LayoutDashboard,
    label: '仪表盘',
    path: PATHS.ADMIN_DASHBOARD,
  },

  // 开始办案 - 菜单组
  {
    id: 'business',
    label: '开始办案',
    icon: Briefcase,
    items: [
      {
        id: 'clients',
        icon: Users,
        label: '当事人',
        path: PATHS.ADMIN_CLIENTS,
      },
      {
        id: 'contracts',
        icon: FileText,
        label: '合同',
        path: PATHS.ADMIN_CONTRACTS,
      },
      {
        id: 'cases',
        icon: Briefcase,
        label: '案件',
        path: PATHS.ADMIN_CASES,
      },
    ],
  },

  // 自动化工具 - 菜单组
  {
    id: 'automation',
    label: '自动化工具',
    icon: Zap,
    items: [
      {
        id: 'preservation-quotes',
        icon: Shield,
        label: '财产保全询价',
        path: PATHS.ADMIN_AUTOMATION_QUOTES,
      },
      {
        id: 'document-recognition',
        icon: FileSearch,
        label: '文书智能识别',
        path: PATHS.ADMIN_AUTOMATION_RECOGNITION,
      },
    ],
  },

  // 设置 - 菜单组
  {
    id: 'settings',
    label: '设置',
    icon: Settings,
    items: [
      {
        id: 'user-settings',
        icon: User,
        label: '用户设置',
        path: PATHS.ADMIN_SETTINGS_USER,
      },
      {
        id: 'system-settings',
        icon: Cog,
        label: '系统配置',
        path: PATHS.ADMIN_SETTINGS_SYSTEM,
      },
    ],
  },
]

/**
 * 获取所有菜单路径（用于路由匹配）
 */
export function getAllMenuPaths(): string[] {
  const paths: string[] = []

  menuConfig.forEach((item) => {
    if (isMenuGroup(item)) {
      item.items.forEach((subItem) => {
        paths.push(subItem.path)
      })
    } else {
      paths.push(item.path)
    }
  })

  return paths
}

/**
 * 根据路径查找所属的菜单组 ID
 */
export function findGroupByPath(pathname: string): string | null {
  for (const item of menuConfig) {
    if (isMenuGroup(item)) {
      for (const subItem of item.items) {
        if (pathname.startsWith(subItem.path)) {
          return item.id
        }
      }
    }
  }
  return null
}
