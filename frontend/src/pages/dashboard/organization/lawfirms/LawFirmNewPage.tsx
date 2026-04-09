/**
 * LawFirmNewPage - 新建律所页面
 *
 * 渲染律所创建表单，配置静态面包屑。
 *
 * 路由: /admin/organization/lawfirms/new
 *
 * @validates Requirements 7.3 - THE System SHALL 在 `/admin/organization/lawfirms/new` 路径显示新建律所页面
 * @validates Requirements 9.4 - THE Breadcrumb SHALL 在新建律所页显示「首页 / 组织管理 / 律所 / 新建」
 */

import { useMemo } from 'react'

import { LawFirmForm } from '@/features/organization/components/LawFirmForm'
import { useBreadcrumb } from '@/contexts/BreadcrumbContext'
import { PATHS } from '@/routes/paths'
import type { BreadcrumbItem } from '@/layouts/components/Breadcrumb'

/**
 * LawFirmNewPage - 新建律所页面组件
 *
 * 功能：
 * 1. 配置静态面包屑显示「首页 / 组织管理 / 律所 / 新建」
 * 2. 渲染 LawFirmForm 组件（创建模式）
 */
export function LawFirmNewPage() {
  // 构建面包屑项
  // Requirements 9.4: 显示「首页 / 组织管理 / 律所 / 新建」
  const breadcrumbItems = useMemo<BreadcrumbItem[]>(
    () => [
      { label: '首页', path: PATHS.ADMIN_DASHBOARD },
      { label: '组织管理', path: PATHS.ADMIN_ORGANIZATION },
      { label: '律所', path: PATHS.ADMIN_LAWFIRMS },
      { label: '新建' }, // 当前页面，无链接
    ],
    []
  )

  // 设置自定义面包屑
  useBreadcrumb(breadcrumbItems)

  // 渲染创建表单组件（不传 lawFirmId，使用 create 模式）
  return <LawFirmForm mode="create" />
}

export default LawFirmNewPage
