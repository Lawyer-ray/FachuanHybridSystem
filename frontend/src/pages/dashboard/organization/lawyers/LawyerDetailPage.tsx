/**
 * LawyerDetailPage - 律师详情页面
 *
 * 渲染律师详情组件，配置动态面包屑（显示律师姓名）。
 *
 * 路由: /admin/organization/lawyers/:id
 *
 * @validates Requirements 7.8 - THE System SHALL 在 `/admin/organization/lawyers/:id` 路径显示律师详情页面
 * @validates Requirements 9.5 - THE Breadcrumb SHALL 在律师详情页显示「首页 / 组织管理 / 律师 / {律师姓名}」
 */

import { useMemo } from 'react'
import { useParams } from 'react-router'

import { LawyerDetail } from '@/features/organization/components/LawyerDetail'
import { useLawyer } from '@/features/organization/hooks/use-lawyer'
import { useBreadcrumb } from '@/contexts/BreadcrumbContext'
import { PATHS } from '@/routes/paths'
import type { BreadcrumbItem } from '@/layouts/components/Breadcrumb'

/**
 * LawyerDetailPage - 律师详情页面组件
 *
 * 功能：
 * 1. 从路由参数获取律师 ID
 * 2. 使用 useLawyer hook 获取律师数据
 * 3. 配置动态面包屑显示「首页 / 组织管理 / 律师 / {律师姓名}」
 * 4. 渲染 LawyerDetail 组件
 */
export function LawyerDetailPage() {
  // 从路由参数获取律师 ID
  const { id } = useParams<{ id: string }>()

  // 获取律师数据用于面包屑显示
  const { data: lawyer } = useLawyer(id!)

  // 构建动态面包屑项
  // Requirements 9.5: 显示「首页 / 组织管理 / 律师 / {律师姓名}」
  const breadcrumbItems = useMemo<BreadcrumbItem[] | null>(() => {
    // 数据加载中时返回 null，使用默认面包屑
    if (!lawyer) return null

    // 显示 real_name（真实姓名），如果没有则显示 username
    const displayName = lawyer.real_name || lawyer.username

    return [
      { label: '首页', path: PATHS.ADMIN_DASHBOARD },
      { label: '组织管理', path: PATHS.ADMIN_ORGANIZATION },
      { label: '律师', path: PATHS.ADMIN_LAWYERS },
      { label: displayName }, // 当前页面，显示律师姓名，无链接
    ]
  }, [lawyer])

  // 设置自定义面包屑
  useBreadcrumb(breadcrumbItems)

  // 渲染详情组件
  // LawyerDetail 组件内部处理加载状态和错误状态
  return <LawyerDetail lawyerId={id!} />
}

export default LawyerDetailPage
