/**
 * OrganizationPage - 组织管理主页面
 *
 * 渲染组织管理 Tab 切换组件，配置静态面包屑。
 *
 * 路由: /admin/organization
 *
 * @validates Requirements 1.1 - THE Organization_Page SHALL 显示四个 Tab：律所、律师、团队、凭证
 * @validates Requirements 1.4 - THE Organization_Page SHALL 页面标题显示「组织管理」
 * @validates Requirements 1.5 - THE Organization_Page SHALL 面包屑显示「首页 > 组织管理」
 * @validates Requirements 9.1 - THE Breadcrumb SHALL 在组织管理主页显示「首页 / 组织管理」
 */

import { useMemo } from 'react'

import { OrganizationTabs } from '@/features/organization/components/OrganizationTabs'
import { useBreadcrumb } from '@/contexts/BreadcrumbContext'
import { PATHS } from '@/routes/paths'
import type { BreadcrumbItem } from '@/layouts/components/Breadcrumb'

/**
 * OrganizationPage - 组织管理主页面组件
 *
 * 功能：
 * 1. 配置静态面包屑显示「首页 / 组织管理」
 * 2. 渲染 OrganizationTabs 组件（Tab 切换）
 * 3. 从 URL 参数读取 activeTab（由 OrganizationTabs 内部处理）
 */
export function OrganizationPage() {
  // 构建面包屑项
  // Requirements 1.5, 9.1: 显示「首页 / 组织管理」
  const breadcrumbItems = useMemo<BreadcrumbItem[]>(
    () => [
      { label: '首页', path: PATHS.ADMIN_DASHBOARD },
      { label: '组织管理' }, // 当前页面，无链接
    ],
    []
  )

  // 设置自定义面包屑
  useBreadcrumb(breadcrumbItems)

  // 渲染组织管理 Tab 组件
  // Requirements 1.1: 显示四个 Tab：律所、律师、团队、凭证
  return (
    <div className="space-y-6">
      {/* 页面标题 - Requirements 1.4 */}
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">组织管理</h1>
        <p className="text-muted-foreground">
          管理律所、律师、团队和账号凭证信息
        </p>
      </div>

      {/* Tab 切换组件 */}
      <OrganizationTabs />
    </div>
  )
}

export default OrganizationPage
