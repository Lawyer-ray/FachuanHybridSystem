/**
 * ClientNewPage - 新建当事人页面
 *
 * 渲染当事人创建表单，配置静态面包屑。
 *
 * 路由: /admin/clients/new
 *
 * @validates Requirements 2.6 - THE Breadcrumb SHALL 在新建当事人页显示「首页 / 当事人 / 新建」
 * @validates Requirements 8.4 - THE System SHALL 在 `/admin/clients/new` 路径显示新建当事人页
 */

import { useMemo } from 'react'

import { ClientForm } from '@/features/clients/components/ClientForm'
import { useBreadcrumb } from '@/contexts/BreadcrumbContext'
import { PATHS } from '@/routes/paths'
import type { BreadcrumbItem } from '@/layouts/components/Breadcrumb'

/**
 * ClientNewPage - 新建当事人页面组件
 *
 * 功能：
 * 1. 配置静态面包屑显示「首页 / 当事人 / 新建」
 * 2. 渲染 ClientForm 组件（创建模式）
 */
export function ClientNewPage() {
  // 构建面包屑项
  // Requirements 2.6: 显示「首页 / 当事人 / 新建」
  const breadcrumbItems = useMemo<BreadcrumbItem[]>(
    () => [
      { label: '首页', path: PATHS.ADMIN_DASHBOARD },
      { label: '当事人', path: PATHS.ADMIN_CLIENTS },
      { label: '新建' }, // 当前页面，无链接
    ],
    []
  )

  // 设置自定义面包屑
  useBreadcrumb(breadcrumbItems)

  // 渲染创建表单组件
  return <ClientForm mode="create" />
}

export default ClientNewPage
