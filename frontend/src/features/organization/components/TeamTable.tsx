/**
 * TeamTable Component
 *
 * 团队列表表格组件
 * - 显示团队名称、团队类型、所属律所列
 * - 实现编辑和删除按钮（非行点击导航）
 * - 支持加载状态和空状态
 * - 移动端支持横向滚动
 *
 * Requirements: 4.1, 4.2, 4.5, 4.6, 4.7
 */

import { Edit2, Trash2, Users } from 'lucide-react'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
import { type Team, type LawFirm, TEAM_TYPE_LABELS } from '../types'

// ============================================================================
// Types
// ============================================================================

export interface TeamTableProps {
  /** 团队列表数据 */
  teams: Team[]
  /** 律所列表（用于查找律所名称） */
  lawFirms: LawFirm[]
  /** 是否正在加载 */
  isLoading?: boolean
  /** 编辑回调 */
  onEdit: (team: Team) => void
  /** 删除回调 */
  onDelete: (team: Team) => void
}

// ============================================================================
// Sub-components
// ============================================================================

/**
 * 表格骨架屏 - 加载状态
 * Requirements: 4.7
 */
function TableSkeleton() {
  return (
    <>
      {Array.from({ length: 5 }).map((_, index) => (
        <TableRow key={index}>
          <TableCell>
            <div className="bg-muted h-4 w-32 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-20 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted h-4 w-28 animate-pulse rounded" />
          </TableCell>
          <TableCell>
            <div className="bg-muted flex h-4 w-20 animate-pulse gap-2 rounded" />
          </TableCell>
        </TableRow>
      ))}
    </>
  )
}

/**
 * 空状态组件
 */
function EmptyState() {
  return (
    <TableRow>
      <TableCell colSpan={4} className="h-48">
        <div className="flex flex-col items-center justify-center gap-3">
          <div className="bg-muted flex size-12 items-center justify-center rounded-full">
            <Users className="text-muted-foreground size-6" />
          </div>
          <div className="text-center">
            <p className="text-muted-foreground text-sm font-medium">
              暂无团队数据
            </p>
            <p className="text-muted-foreground/70 mt-1 text-xs">
              点击「新建团队」按钮添加第一个团队
            </p>
          </div>
        </div>
      </TableCell>
    </TableRow>
  )
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 团队表格组件
 *
 * Requirements:
 * - 4.1: 以表格形式展示团队列表
 * - 4.2: 显示团队名称、团队类型、所属律所列
 * - 4.5: 实现编辑按钮
 * - 4.6: 实现删除按钮
 * - 4.7: 数据加载时显示加载状态
 * - 6.2: 屏幕宽度小于 768px 时表格支持横向滚动
 */
export function TeamTable({
  teams,
  lawFirms,
  isLoading = false,
  onEdit,
  onDelete,
}: TeamTableProps) {
  /**
   * 根据律所 ID 查找律所名称
   */
  const getLawFirmName = (lawFirmId: number): string => {
    const lawFirm = lawFirms.find((lf) => lf.id === lawFirmId)
    return lawFirm?.name ?? '-'
  }

  return (
    // 外层容器：支持横向滚动 - Requirements: 6.2
    <div className="overflow-x-auto rounded-md border">
      {/* 表格设置最小宽度，确保在小屏幕上不会过度压缩 */}
      <Table className="min-w-[500px]">
        {/* 表头 - Requirements: 4.2 */}
        <TableHeader>
          <TableRow>
            <TableHead className="w-[140px] text-xs sm:w-[180px] sm:text-sm">
              团队名称
            </TableHead>
            <TableHead className="w-[100px] text-xs sm:w-[120px] sm:text-sm">
              团队类型
            </TableHead>
            <TableHead className="w-[140px] text-xs sm:w-[180px] sm:text-sm">
              所属律所
            </TableHead>
            <TableHead className="w-[100px] text-xs sm:w-[120px] sm:text-sm">
              操作
            </TableHead>
          </TableRow>
        </TableHeader>

        {/* 表体 - Requirements: 4.1, 4.5, 4.6, 4.7 */}
        <TableBody>
          {isLoading ? (
            <TableSkeleton />
          ) : teams.length === 0 ? (
            <EmptyState />
          ) : (
            teams.map((team) => (
              <TableRow
                key={team.id}
                // 触摸友好的行高 - 最小 44px 点击区域
                className="h-11 sm:h-auto"
              >
                <TableCell className="text-xs font-medium sm:text-sm">
                  {team.name || '-'}
                </TableCell>
                <TableCell className="text-muted-foreground text-xs sm:text-sm">
                  {TEAM_TYPE_LABELS[team.team_type]}
                </TableCell>
                <TableCell className="text-muted-foreground text-xs sm:text-sm">
                  {getLawFirmName(team.law_firm)}
                </TableCell>
                <TableCell>
                  <div className="flex items-center gap-1">
                    {/* 编辑按钮 - Requirements: 4.5 */}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-8"
                      onClick={() => onEdit(team)}
                      aria-label={`编辑团队 ${team.name}`}
                    >
                      <Edit2 className="size-4" />
                    </Button>
                    {/* 删除按钮 - Requirements: 4.6 */}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="text-destructive hover:text-destructive size-8"
                      onClick={() => onDelete(team)}
                      aria-label={`删除团队 ${team.name}`}
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
