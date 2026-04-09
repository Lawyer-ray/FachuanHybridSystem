/**
 * LawyerNewPage - 新建律师页面
 *
 * 渲染律师创建表单，配置静态面包屑。
 *
 * 路由: /admin/organization/lawyers/new
 *
 * @validates Requirements 7.7 - THE System SHALL 在 `/admin/organization/lawyers/new` 路径显示新建律师页面
 * @validates Requirements 9.7 - THE Breadcrumb SHALL 在新建律师页显示「首页 / 组织管理 / 律师 / 新建」
 */

import { useMemo } from 'react'

import { LawyerForm } from '@/features/organization/components/LawyerForm'
import { useBreadcrumb } from '@/contexts/BreadcrumbContext'
import { PATHS } from '@/routes/paths'
import type { BreadcrumbItem } from '@/layouts/components/Breadcrumb'

/**
 * LawyerNewPage - 新建律师页面组件
 *
 * 功能：
 * 1. 配置静态面包屑显示「首页 / 组织管理 / 律师 / 新建」
 * 2. 渲染 LawyerForm 组件（创建模式）
 */
export function LawyerNewPage() {
  // 构建面包屑项
  // Requirements 9.7: 显示「首页 / 组织管理 / 律师 / 新建」
  const breadcrumbItems = useMemo<BreadcrumbItem[]>(
    () => [
      { label: '首页', path: PATHS.ADMIN_DASHBOARD },
      { label: '组织管理', path: PATHS.ADMIN_ORGANIZATION },
      { label: '律师', path: PATHS.ADMIN_LAWYERS },
      { label: '新建' }, // 当前页面，无链接
    ],
    []
  )

  // 设置自定义面包屑
  useBreadcrumb(breadcrumbItems)

  // 渲染创建表单组件（不传 lawyerId，使用 create 模式）
  return <LawyerForm mode="create" />
}

export default LawyerNewPage
