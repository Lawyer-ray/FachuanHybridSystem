/**
 * TeamList Component
 *
 * 团队列表组件
 * - 组合 TeamTable 和 TeamFormDialog 组件
 * - 实现类型筛选下拉框（全部、律师团队、业务团队）
 * - 实现「新建团队」按钮打开新建对话框
 * - 实现删除确认对话框
 * - 管理对话框状态（创建、编辑、删除）
 *
 * Requirements:
 * - 4.3: 实现类型筛选下拉框
 * - 4.4: 实现新建按钮
 * - 4.15: 删除前显示确认对话框
 * - 4.16: 确认删除后删除团队并显示成功提示
 */

import { useState, useCallback } from 'react'
import { Plus, Trash2 } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog'

import { TeamTable } from './TeamTable'
import { TeamFormDialog } from './TeamFormDialog'
import { useTeams } from '../hooks/use-teams'
import { useTeamMutations } from '../hooks/use-team-mutations'
import { useLawFirms } from '../hooks/use-lawfirms'
import type { Team, TeamType } from '../types'
import { TEAM_TYPE_LABELS } from '../types'

// ============================================================================
// Constants
// ============================================================================

/** 筛选下拉框的「全部」选项值 */
const ALL_TYPES_VALUE = 'all'

// ============================================================================
// Types
// ============================================================================

export interface TeamListProps {
  // 无需 props，内部管理状态
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 团队列表组件
 */
export function TeamList(_props: TeamListProps) {
  // ========== 筛选状态 ==========
  const [teamType, setTeamType] = useState<TeamType | undefined>(undefined)

  // ========== 对话框状态 ==========
  const [formDialogOpen, setFormDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [selectedTeam, setSelectedTeam] = useState<Team | undefined>(undefined)

  // ========== 数据查询 ==========
  const { data: teams, isLoading: isLoadingTeams } = useTeams({
    teamType: teamType,
  })
  const { data: lawFirms } = useLawFirms()
  const { deleteTeam } = useTeamMutations()

  // ========== 事件处理 ==========

  const handleTypeFilterChange = useCallback((value: string) => {
    if (value === ALL_TYPES_VALUE) {
      setTeamType(undefined)
    } else {
      setTeamType(value as TeamType)
    }
  }, [])

  const handleCreateClick = useCallback(() => {
    setSelectedTeam(undefined)
    setFormDialogOpen(true)
  }, [])

  const handleEditClick = useCallback((team: Team) => {
    setSelectedTeam(team)
    setFormDialogOpen(true)
  }, [])

  const handleDeleteClick = useCallback((team: Team) => {
    setSelectedTeam(team)
    setDeleteDialogOpen(true)
  }, [])

  const handleConfirmDelete = useCallback(() => {
    if (!selectedTeam) return

    deleteTeam.mutate(selectedTeam.id, {
      onSuccess: () => {
        toast.success('团队删除成功')
        setDeleteDialogOpen(false)
        setSelectedTeam(undefined)
      },
      onError: (error) => {
        const errorMessage =
          error instanceof Error ? error.message : '删除失败，请重试'
        toast.error(errorMessage)
      },
    })
  }, [selectedTeam, deleteTeam])

  const handleCancelDelete = useCallback(() => {
    setDeleteDialogOpen(false)
    setSelectedTeam(undefined)
  }, [])

  const handleFormDialogOpenChange = useCallback((open: boolean) => {
    setFormDialogOpen(open)
    if (!open) {
      setSelectedTeam(undefined)
    }
  }, [])

  // ========== 渲染 ==========
  return (
    <div className="flex flex-col gap-4">
      {/* 顶部操作栏 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {/* 类型筛选 */}
        <div className="w-full sm:w-[180px]">
          <Select
            value={teamType ?? ALL_TYPES_VALUE}
            onValueChange={handleTypeFilterChange}
          >
            <SelectTrigger className="h-10 w-full">
              <SelectValue placeholder="选择团队类型" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_TYPES_VALUE}>全部</SelectItem>
              {(Object.keys(TEAM_TYPE_LABELS) as TeamType[]).map((type) => (
                <SelectItem key={type} value={type}>
                  {TEAM_TYPE_LABELS[type]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* 新建按钮 */}
        <Button onClick={handleCreateClick} className="w-full sm:w-auto">
          <Plus className="mr-2 size-4" />
          新建团队
        </Button>
      </div>

      {/* 表格 */}
      <TeamTable
        teams={teams ?? []}
        lawFirms={lawFirms ?? []}
        isLoading={isLoadingTeams}
        onEdit={handleEditClick}
        onDelete={handleDeleteClick}
      />

      {/* 表单对话框 */}
      <TeamFormDialog
        open={formDialogOpen}
        onOpenChange={handleFormDialogOpenChange}
        team={selectedTeam}
      />

      {/* 删除确认对话框 */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <div className="bg-destructive/10 text-destructive mx-auto mb-4 flex size-12 items-center justify-center rounded-full">
              <Trash2 className="size-6" />
            </div>
            <AlertDialogTitle className="text-center">
              确认删除团队
            </AlertDialogTitle>
            <AlertDialogDescription className="text-center">
              您确定要删除团队「{selectedTeam?.name}」吗？此操作无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="sm:justify-center">
            <AlertDialogCancel
              onClick={handleCancelDelete}
              disabled={deleteTeam.isPending}
            >
              取消
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              disabled={deleteTeam.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteTeam.isPending ? '删除中...' : '确认删除'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default TeamList
