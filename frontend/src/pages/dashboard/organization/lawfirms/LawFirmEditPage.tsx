/**
 * LawFirmEditPage - 律所编辑页面
 *
 * 渲染律所表单组件（编辑模式），配置动态面包屑（显示律所名称）。
 *
 * 路由: /admin/organization/lawfirms/:id/edit
 *
 * @validates Requirements 7.5 - THE System SHALL 在 `/admin/organization/lawfirms/:id/edit` 路径显示编辑律所页面
 * @validates Requirements 9.3 - THE Breadcrumb SHALL 在律所编辑页显示「首页 / 组织管理 / 律所 / {律所名称} / 编辑」
 */

import { useMemo } from 'react'
import { useParams } from 'react-router'

import { LawFirmForm } from '@/features/organization/components/LawFirmForm'
import { useLawFirm } from '@/features/organization/hooks/use-lawfirm'
import { useBreadcrumb } from '@/contexts/BreadcrumbContext'
import { PATHS, generatePath } from '@/routes/paths'
import type { BreadcrumbItem } from '@/layouts/components/Breadcrumb'

/**
 * LawFirmEditPage - 律所编辑页面组件
 *
 * 功能：
 * 1. 从路由参数获取律所 ID
 * 2. 使用 useLawFirm hook 获取律所数据用于面包屑显示
 * 3. 配置动态面包屑显示「首页 / 组织管理 / 律所 / {律所名称} / 编辑」
 * 4. 渲染 LawFirmForm 组件（编辑模式）
 */
export function LawFirmEditPage() {
  // 从路由参数获取律所 ID
  const { id } = useParams<{ id: string }>()

  // 获取律所数据用于面包屑显示
  const { data: lawFirm } = useLawFirm(id!)

  // 构建动态面包屑项
  // Requirements 9.3: 显示「首页 / 组织管理 / 律所 / {律所名称} / 编辑」
  const breadcrumbItems = useMemo<BreadcrumbItem[] | null>(() => {
    // 数据加载中时返回 null，使用默认面包屑
    if (!lawFirm) return null

    return [
      { label: '首页', path: PATHS.ADMIN_DASHBOARD },
      { label: '组织管理', path: PATHS.ADMIN_ORGANIZATION },
      { label: '律所', path: PATHS.ADMIN_LAWFIRMS },
      { label: lawFirm.name, path: generatePath.lawFirmDetail(lawFirm.id) },
      { label: '编辑' }, // 当前页面，无链接
    ]
  }, [lawFirm])

  // 设置自定义面包屑
  useBreadcrumb(breadcrumbItems)

  // 渲染表单组件（编辑模式）
  // LawFirmForm 组件内部处理加载状态和错误状态
  return <LawFirmForm lawFirmId={id} mode="edit" />
}

export default LawFirmEditPage
