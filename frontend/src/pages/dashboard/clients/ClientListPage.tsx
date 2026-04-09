/**
 * ClientListPage - 当事人列表页面
 *
 * 渲染当事人列表组件，面包屑由 AdminLayout 自动处理。
 *
 * 路由: /admin/clients
 *
 * @validates Requirements 2.3 - THE Breadcrumb SHALL 在当事人列表页显示「首页 / 当事人」
 * @validates Requirements 8.1 - THE System SHALL 在 `/admin/clients` 路径显示当事人列表页
 */

import { ClientList } from '@/features/clients/components/ClientList'

export function ClientListPage() {
  return <ClientList />
}

export default ClientListPage
