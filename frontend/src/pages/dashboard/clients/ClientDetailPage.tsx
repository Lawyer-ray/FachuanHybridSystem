/**
 * ClientDetailPage - 当事人详情页面
 *
 * 渲染当事人详情组件，配置动态面包屑显示当事人姓名。
 *
 * 路由: /admin/clients/:id
 *
 * @validates Requirements 2.4 - THE Breadcrumb SHALL 在当事人详情页显示「首页 / 当事人 / {当事人姓名}」
 * @validates Requirements 8.2 - THE System SHALL 在 `/admin/clients/:id` 路径显示当事人详情页
 */

import { useMemo } from 'react'
import { useParams } from 'react-router'

import { ClientDetail } from '@/features/clients/components/ClientDetail'
import { useClient } from '@/features/clients/hooks/use-client'
import { useBreadcrumb } from '@/contexts/BreadcrumbContext'
import { PATHS } from '@/routes/paths'
import type { BreadcrumbItem } from '@/layouts/components/Breadcrumb'

/**
 * ClientDetailPage - 当事人详情页面组件
 *
 * 功能：
 * 1. 从路由参数获取当事人 ID
 * 2. 使用 useClient hook 获取当事人数据
 * 3. 配置动态面包屑显示当事人姓名
 * 4. 渲染 ClientDetail 组件
 */
export function ClientDetailPage() {
  // 从路由参数获取当事人 ID
  const { id } = useParams<{ id: string }>()

  // 获取当事人数据用于面包屑显示
  const { data: client } = useClient(id!)

  // 构建面包屑项
  // Requirements 2.4: 显示「首页 / 当事人 / {当事人姓名}」
  const breadcrumbItems = useMemo<BreadcrumbItem[] | null>(() => {
    // 数据加载中时返回 null，使用默认面包屑
    if (!client) {
      return null
    }

    return [
      { label: '首页', path: PATHS.ADMIN_DASHBOARD },
      { label: '当事人', path: PATHS.ADMIN_CLIENTS },
      { label: client.name }, // 当前页面，无链接
    ]
  }, [client])

  // 设置自定义面包屑
  useBreadcrumb(breadcrumbItems)

  // 渲染详情组件
  return <ClientDetail clientId={id!} />
}

export default ClientDetailPage
