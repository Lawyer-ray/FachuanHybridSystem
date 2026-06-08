/**
 * 菜单配置
 * 统一管理侧边栏菜单结构（v4 设计）
 */

import {
  LayoutDashboard,
  Briefcase,
  FileText,
  Users,
  Zap,
  MessageSquare,
  Truck,
  ArrowRightLeft,
  Calculator,
  Settings,
  Bot,
  type LucideIcon,
} from 'lucide-react'
import { PATHS } from '@/routes/paths'

export interface MenuItem {
  id: string
  icon: LucideIcon
  label: string
  path: string
  badge?: number
}

export interface MenuGroup {
  id: string
  label: string
  icon?: LucideIcon
  items: MenuItem[]
}

export interface TopLevelMenuItem {
  id: string
  icon: LucideIcon
  label: string
  path: string
  badge?: number
}

export type MenuConfig = (TopLevelMenuItem | MenuGroup)[]

export function isMenuGroup(item: TopLevelMenuItem | MenuGroup): item is MenuGroup {
  return 'items' in item
}

export const menuConfig: MenuConfig = [
  // 仪表盘 - 顶级置顶
  {
    id: 'dashboard',
    icon: LayoutDashboard,
    label: '仪表盘',
    path: PATHS.ADMIN_DASHBOARD,
  },
  // 工作台 - AI 对话
  {
    id: 'workbench',
    icon: Bot,
    label: '工作台',
    path: PATHS.ADMIN_WORKBENCH,
  },

  // 业务 - 菜单组
  {
    id: 'business',
    label: '业务',
    icon: Briefcase,
    items: [
      {
        id: 'clients',
        icon: Users,
        label: '当事人管理',
        path: PATHS.ADMIN_CLIENTS,
      },
      {
        id: 'contracts',
        icon: FileText,
        label: '合同管理',
        path: PATHS.ADMIN_CONTRACTS,
      },
      {
        id: 'cases',
        icon: Briefcase,
        label: '案件管理',
        path: PATHS.ADMIN_CASES,
      },
    ],
  },

  // 工具 - 菜单组
  {
    id: 'tools',
    label: '工具',
    icon: Zap,
    items: [
      {
        id: 'court-sms',
        icon: MessageSquare,
        label: '法院短信',
        path: PATHS.ADMIN_TOOLS_COURT_SMS,
      },
      {
        id: 'courier-tracking',
        icon: Truck,
        label: '快递查询',
        path: PATHS.ADMIN_TOOLS_COURIER,
      },
      {
        id: 'element-convert',
        icon: ArrowRightLeft,
        label: '要素式转换',
        path: PATHS.ADMIN_TOOLS_ELEMENT,
      },
      {
        id: 'lpr-calculator',
        icon: Calculator,
        label: 'LPR 计算器',
        path: PATHS.ADMIN_TOOLS_LPR,
      },
    ],
  },
]

// 底部固定菜单项
export const bottomMenuItems: TopLevelMenuItem[] = [
  {
    id: 'settings',
    icon: Settings,
    label: '系统设置',
    path: PATHS.ADMIN_SETTINGS,
  },
]

export function getAllMenuPaths(): string[] {
  const paths: string[] = []
  menuConfig.forEach((item) => {
    if (isMenuGroup(item)) {
      item.items.forEach((subItem) => paths.push(subItem.path))
    } else {
      paths.push(item.path)
    }
  })
  bottomMenuItems.forEach((item) => paths.push(item.path))
  return paths
}

export function findGroupByPath(pathname: string): string | null {
  for (const item of menuConfig) {
    if (isMenuGroup(item)) {
      for (const subItem of item.items) {
        if (pathname.startsWith(subItem.path)) return item.id
      }
    }
  }
  return null
}
