/**
 * LawFirmDetailPage - 律所详情页面
 *
 * 渲染律所详情组件，配置动态面包屑（显示律所名称）。
 *
 * 路由: /admin/organization/lawfirms/:id
 *
 * @validates Requirements 7.4 - THE System SHALL 在 `/admin/organization/lawfirms/:id` 路径显示律所详情页面
 * @validates Requirements 9.2 - THE Breadcrumb SHALL 在律所详情页显示「首页 / 组织管理 / 律所 / {律所名称}」
 */

import { useMemo } from 'react'
import { useParams } from 'react-router'

import { LawFirmDetail } from '@/features/organization/components/LawFirmDetail'
import { useLawFirm } from '@/features/organization/hooks/use-lawfirm'
import { useBreadcrumb } from '@/contexts/BreadcrumbContext'
import { PATHS } from '@/routes/paths'
import type { BreadcrumbItem } from '@/layouts/components/Breadcrumb'

/**
 * LawFirmDetailPage - 律所详情页面组件
 *
 * 功能：
 * 1. 从路由参数获取律所 ID
 * 2. 使用 useLawFirm hook 获取律所数据
 * 3. 配置动态面包屑显示「首页 / 组织管理 / 律所 / {律所名称}」
 * 4. 渲染 LawFirmDetail 组件
 */
export function LawFirmDetailPage() {
  // 从路由参数获取律所 ID
  const { id } = useParams<{ id: string }>()

  // 获取律所数据用于面包屑显示
  const { data: lawFirm } = useLawFirm(id!)

  // 构建动态面包屑项
  // Requirements 9.2: 显示「首页 / 组织管理 / 律所 / {律所名称}」
  const breadcrumbItems = useMemo<BreadcrumbItem[] | null>(() => {
    // 数据加载中时返回 null，使用默认面包屑
    if (!lawFirm) return null

    return [
      { label: '首页', path: PATHS.ADMIN_DASHBOARD },
      { label: '组织管理', path: PATHS.ADMIN_ORGANIZATION },
      { label: '律所', path: PATHS.ADMIN_LAWFIRMS },
      { label: lawFirm.name }, // 当前页面，显示律所名称，无链接
    ]
  }, [lawFirm])

  // 设置自定义面包屑
  useBreadcrumb(breadcrumbItems)

  // 渲染详情组件
  // LawFirmDetail 组件内部处理加载状态和错误状态
  return <LawFirmDetail lawFirmId={id!} />
}

export default LawFirmDetailPage
