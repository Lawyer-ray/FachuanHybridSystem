/**
 * LawyerList Component
 *
 * 律师列表组件
 * - 组合 LawyerFilters 和 LawyerTable 组件
 * - 实现「新建律师」按钮导航到新建页面
 * - 使用 useLawyers hook 获取数据，支持搜索参数
 * - 管理搜索状态并传递给 useLawyers hook
 *
 * Requirements: 3.4
 */

import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router'
import { Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PATHS } from '@/routes/paths'

import { LawyerFilters } from './LawyerFilters'
import { LawyerTable } from './LawyerTable'
import { useLawyers } from '../hooks/use-lawyers'

// ============================================================================
// Types
// ============================================================================

export interface LawyerListProps {
  // 无需 props，内部管理状态
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 律师列表组件
 *
 * Requirements:
 * - 3.4: 点击「新建律师」按钮导航到新建页面
 * - 3.3: 提供搜索框支持按用户名、真实姓名、手机号搜索
 */
export function LawyerList(_props: LawyerListProps) {
  const navigate = useNavigate()

  // ========== 状态管理 ==========
  /** 搜索关键词状态 */
  const [search, setSearch] = useState('')

  // ========== 数据查询 ==========
  /** 使用 useLawyers hook 获取数据，传入搜索参数 */
  const { data: lawyers, isLoading } = useLawyers({ search })

  // ========== 事件处理 ==========

  /**
   * 处理新建按钮点击
   * Requirements: 3.4
   */
  const handleCreateClick = useCallback(() => {
    navigate(PATHS.ADMIN_LAWYER_NEW)
  }, [navigate])

  /**
   * 处理搜索关键词变化
   * Requirements: 3.3
   */
  const handleSearchChange = useCallback((value: string) => {
    setSearch(value)
  }, [])

  // ========== 渲染 ==========
  return (
    <div className="flex flex-col gap-4">
      {/* 顶部操作栏：筛选器 + 新建按钮 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {/* 左侧：筛选器 - Requirements: 3.3 */}
        <LawyerFilters search={search} onSearchChange={handleSearchChange} />

        {/* 右侧：新建按钮 - Requirements: 3.4 */}
        <Button onClick={handleCreateClick} className="w-full sm:w-auto">
          <Plus className="mr-2 size-4" />
          新建律师
        </Button>
      </div>

      {/* 表格 */}
      <LawyerTable lawyers={lawyers ?? []} isLoading={isLoading} />
    </div>
  )
}

export default LawyerList
