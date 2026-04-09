/**
 * LawyerEditPage - 律师编辑页面
 *
 * 渲染律师表单组件（编辑模式），配置动态面包屑（显示律师姓名）。
 *
 * 路由: /admin/organization/lawyers/:id/edit
 *
 * @validates Requirements 7.9 - THE System SHALL 在 `/admin/organization/lawyers/:id/edit` 路径显示编辑律师页面
 * @validates Requirements 9.6 - THE Breadcrumb SHALL 在律师编辑页显示「首页 / 组织管理 / 律师 / {律师姓名} / 编辑」
 */

import { useMemo } from 'react'
import { useParams } from 'react-router'

import { LawyerForm } from '@/features/organization/components/LawyerForm'
import { useLawyer } from '@/features/organization/hooks/use-lawyer'
import { useBreadcrumb } from '@/contexts/BreadcrumbContext'
import { PATHS, generatePath } from '@/routes/paths'
import type { BreadcrumbItem } from '@/layouts/components/Breadcrumb'

/**
 * LawyerEditPage - 律师编辑页面组件
 *
 * 功能：
 * 1. 从路由参数获取律师 ID
 * 2. 使用 useLawyer hook 获取律师数据用于面包屑显示
 * 3. 配置动态面包屑显示「首页 / 组织管理 / 律师 / {律师姓名} / 编辑」
 * 4. 渲染 LawyerForm 组件（编辑模式）
 */
export function LawyerEditPage() {
  // 从路由参数获取律师 ID
  const { id } = useParams<{ id: string }>()

  // 获取律师数据用于面包屑显示
  const { data: lawyer } = useLawyer(id!)

  // 构建动态面包屑项
  // Requirements 9.6: 显示「首页 / 组织管理 / 律师 / {律师姓名} / 编辑」
  // 优先显示 real_name，如果没有则显示 username
  const breadcrumbItems = useMemo<BreadcrumbItem[] | null>(() => {
    // 数据加载中时返回 null，使用默认面包屑
    if (!lawyer) return null

    // 显示 real_name（如果有），否则显示 username
    const displayName = lawyer.real_name || lawyer.username

    return [
      { label: '首页', path: PATHS.ADMIN_DASHBOARD },
      { label: '组织管理', path: PATHS.ADMIN_ORGANIZATION },
      { label: '律师', path: PATHS.ADMIN_LAWYERS },
      { label: displayName, path: generatePath.lawyerDetail(lawyer.id) },
      { label: '编辑' }, // 当前页面，无链接
    ]
  }, [lawyer])

  // 设置自定义面包屑
  useBreadcrumb(breadcrumbItems)

  // 渲染表单组件（编辑模式）
  // LawyerForm 组件内部处理加载状态和错误状态
  return <LawyerForm lawyerId={id} mode="edit" />
}

export default LawyerEditPage
