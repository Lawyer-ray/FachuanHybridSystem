/**
 * ClientEditPage - 当事人编辑页面
 *
 * 渲染当事人编辑表单，配置动态面包屑显示当事人姓名。
 *
 * 路由: /admin/clients/:id/edit
 *
 * @validates Requirements 2.5 - THE Breadcrumb SHALL 在当事人编辑页显示「首页 / 当事人 / {当事人姓名} / 编辑」
 * @validates Requirements 8.3 - THE System SHALL 在 `/admin/clients/:id/edit` 路径显示当事人编辑页
 */

import { useMemo } from 'react'
import { useParams } from 'react-router'

import { ClientForm } from '@/features/clients/components/ClientForm'
import { useClient } from '@/features/clients/hooks/use-client'
import { useBreadcrumb } from '@/contexts/BreadcrumbContext'
import { PATHS, generatePath } from '@/routes/paths'
import type { BreadcrumbItem } from '@/layouts/components/Breadcrumb'

/**
 * ClientEditPage - 当事人编辑页面组件
 *
 * 功能：
 * 1. 从路由参数获取当事人 ID
 * 2. 使用 useClient hook 获取当事人数据
 * 3. 配置动态面包屑显示当事人姓名和编辑标识
 * 4. 渲染 ClientForm 组件（编辑模式）
 */
export function ClientEditPage() {
  // 从路由参数获取当事人 ID
  const { id } = useParams<{ id: string }>()

  // 获取当事人数据用于面包屑显示
  const { data: client } = useClient(id!)

  // 构建面包屑项
  // Requirements 2.5: 显示「首页 / 当事人 / {当事人姓名} / 编辑」
  const breadcrumbItems = useMemo<BreadcrumbItem[] | null>(() => {
    // 数据加载中时返回 null，使用默认面包屑
    if (!client) {
      return null
    }

    return [
      { label: '首页', path: PATHS.ADMIN_DASHBOARD },
      { label: '当事人', path: PATHS.ADMIN_CLIENTS },
      { label: client.name, path: generatePath.clientDetail(client.id) },
      { label: '编辑' }, // 当前页面，无链接
    ]
  }, [client])

  // 设置自定义面包屑
  useBreadcrumb(breadcrumbItems)

  // 渲染编辑表单组件
  return <ClientForm mode="edit" clientId={id!} />
}

export default ClientEditPage
