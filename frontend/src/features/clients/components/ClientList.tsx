/**
 * ClientList Component
 *
 * 当事人列表组件
 * - 组合 ClientFilters 和 ClientTable
 * - 实现分页控件
 * - 实现新建按钮
 *
 * Requirements: 3.5, 3.6
 */

import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PATHS } from '@/routes/paths'
import { PageFooter } from '@/components/shared/PageFooter'

import { ClientFilters } from './ClientFilters'
import { ClientTable } from './ClientTable'
import { useClients } from '../hooks/use-clients'
import type { ClientType } from '../types'

// ============================================================================
// Constants
// ============================================================================

/** 默认每页显示条数 - Requirements: 3.5 */
const DEFAULT_PAGE_SIZE = 20

// ============================================================================
// Main Component
// ============================================================================

/**
 * 当事人列表组件
 *
 * Requirements:
 * - 3.5: 支持分页，每页默认显示 20 条
 * - 3.6: 点击「新建当事人」按钮导航到新建页面
 */
export function ClientList() {
  const navigate = useNavigate()

  // ========== 状态管理 ==========
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [clientType, setClientType] = useState<ClientType | undefined>(undefined)
  const [isOurClient, setIsOurClient] = useState<boolean | undefined>(undefined)

  // ========== 数据查询 ==========
  const { data, isLoading } = useClients({
    page,
    pageSize: DEFAULT_PAGE_SIZE,
    search: search || undefined,
    clientType,
    isOurClient,
  })

  // ========== 事件处理 ==========

  /**
   * 处理搜索变化
   * 搜索时重置到第一页
   */
  const handleSearchChange = useCallback((value: string) => {
    setSearch(value)
    setPage(1)
  }, [])

  /**
   * 处理类型筛选变化
   * 筛选时重置到第一页
   */
  const handleClientTypeChange = useCallback((value: ClientType | undefined) => {
    setClientType(value)
    setPage(1)
  }, [])

  /**
   * 处理我方当事人筛选变化
   */
  const handleIsOurClientChange = useCallback((value: boolean | undefined) => {
    setIsOurClient(value)
    setPage(1)
  }, [])

  /**
   * 处理页码变化
   */
  const handlePageChange = useCallback((newPage: number) => {
    setPage(newPage)
  }, [])

  /**
   * 处理新建按钮点击
   * Requirements: 3.6
   */
  const handleCreateClick = useCallback(() => {
    navigate(PATHS.ADMIN_CLIENT_NEW)
  }, [navigate])

  // ========== 渲染 ==========
  const clients = data?.items ?? []
  const total = data?.total ?? 0

  return (
    <div className="flex flex-col gap-4">
      {/* 顶部操作栏：筛选 + 新建按钮 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <ClientFilters
          search={search}
          onSearchChange={handleSearchChange}
          clientType={clientType}
          onClientTypeChange={handleClientTypeChange}
          isOurClient={isOurClient}
          onIsOurClientChange={handleIsOurClientChange}
        />

        {/* 新建按钮 - Requirements: 3.6 */}
        <Button onClick={handleCreateClick} className="w-full sm:w-auto">
          <Plus className="mr-2 size-4" />
          新建当事人
        </Button>
      </div>

      {/* 表格 */}
      <ClientTable clients={clients} isLoading={isLoading} />

      {/* 分页控件 - Requirements: 3.5 */}
      <PageFooter
        stats={[{ label: '共', value: `${total} 条` }]}
        page={page}
        total={total}
        pageSize={DEFAULT_PAGE_SIZE}
        onPageChange={handlePageChange}
      />
    </div>
  )
}

export default ClientList
