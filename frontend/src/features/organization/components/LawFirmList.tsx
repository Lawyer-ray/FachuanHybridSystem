/**
 * LawFirmList Component
 *
 * 律所列表组件
 * - 组合 LawFirmTable 组件
 * - 实现「新建律所」按钮导航到新建页面
 * - 使用 useLawFirms hook 获取数据
 *
 * Requirements: 2.3
 */

import { useCallback } from 'react'
import { useNavigate } from 'react-router'
import { Plus } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { PATHS } from '@/routes/paths'

import { LawFirmTable } from './LawFirmTable'
import { useLawFirms } from '../hooks/use-lawfirms'

// ============================================================================
// Types
// ============================================================================

export interface LawFirmListProps {
  // 无需 props，内部管理状态
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 律所列表组件
 *
 * Requirements:
 * - 2.3: 点击「新建律所」按钮导航到新建页面
 */
export function LawFirmList(_props: LawFirmListProps) {
  const navigate = useNavigate()

  // ========== 数据查询 ==========
  const { data: lawFirms, isLoading } = useLawFirms()

  // ========== 事件处理 ==========

  /**
   * 处理新建按钮点击
   * Requirements: 2.3
   */
  const handleCreateClick = useCallback(() => {
    navigate(PATHS.ADMIN_LAWFIRM_NEW)
  }, [navigate])

  // ========== 渲染 ==========
  return (
    <div className="flex flex-col gap-4">
      {/* 顶部操作栏：新建按钮 */}
      <div className="flex items-center justify-end">
        {/* 新建按钮 - Requirements: 2.3 */}
        <Button onClick={handleCreateClick} className="w-full sm:w-auto">
          <Plus className="mr-2 size-4" />
          新建律所
        </Button>
      </div>

      {/* 表格 */}
      <LawFirmTable lawFirms={lawFirms ?? []} isLoading={isLoading} />
    </div>
  )
}

export default LawFirmList
