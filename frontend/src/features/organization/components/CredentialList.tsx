/**
 * CredentialList Component
 *
 * 凭证列表组件
 * - 组合 CredentialTable 和 CredentialFormDialog 组件
 * - 实现律师筛选下拉框
 * - 实现「新建凭证」按钮打开新建对话框
 * - 实现删除确认对话框
 * - 管理对话框状态（创建、编辑、删除）
 *
 * Requirements:
 * - 5.3: 提供律师筛选下拉框，筛选特定律师的凭证
 * - 5.4: 提供表单编辑凭证信息
 * - 5.16: 提供删除按钮，点击后显示确认对话框
 * - 5.17: 确认删除后删除凭证并显示成功提示
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

import { CredentialTable } from './CredentialTable'
import { CredentialFormDialog } from './CredentialFormDialog'
import { useCredentials } from '../hooks/use-credentials'
import { useCredentialMutations } from '../hooks/use-credential-mutations'
import { useLawyers } from '../hooks/use-lawyers'
import type { AccountCredential } from '../types'

// ============================================================================
// Constants
// ============================================================================

/** 筛选下拉框的「全部」选项值 */
const ALL_LAWYERS_VALUE = 'all'

// ============================================================================
// Types
// ============================================================================

export interface CredentialListProps {
  // 无需 props，内部管理状态
}

// ============================================================================
// Main Component
// ============================================================================

/**
 * 凭证列表组件
 *
 * Requirements:
 * - 5.3: 提供律师筛选下拉框，筛选特定律师的凭证
 * - 5.4: 提供表单编辑凭证信息
 * - 5.16: 提供删除按钮，点击后显示确认对话框
 * - 5.17: 确认删除后删除凭证并显示成功提示
 */
export function CredentialList(_props: CredentialListProps) {
  // ========== 筛选状态 ==========
  // Requirements: 5.3 - 律师筛选
  const [lawyerId, setLawyerId] = useState<number | undefined>(undefined)

  // ========== 对话框状态 ==========
  const [formDialogOpen, setFormDialogOpen] = useState(false)
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false)
  const [selectedCredential, setSelectedCredential] = useState<
    AccountCredential | undefined
  >(undefined)

  // ========== 数据查询 ==========
  const { data: credentials, isLoading: isLoadingCredentials } = useCredentials(
    {
      lawyerId: lawyerId,
    }
  )
  const { data: lawyers, isLoading: isLoadingLawyers } = useLawyers()
  const { deleteCredential } = useCredentialMutations()

  // ========== 事件处理 ==========

  /**
   * 律师筛选变更处理
   * Requirements: 5.3
   */
  const handleLawyerFilterChange = useCallback((value: string) => {
    if (value === ALL_LAWYERS_VALUE) {
      setLawyerId(undefined)
    } else {
      setLawyerId(Number(value))
    }
  }, [])

  /**
   * 新建按钮点击处理
   * Requirements: 5.4
   */
  const handleCreateClick = useCallback(() => {
    setSelectedCredential(undefined)
    setFormDialogOpen(true)
  }, [])

  /**
   * 编辑按钮点击处理
   * Requirements: 5.4
   */
  const handleEditClick = useCallback((credential: AccountCredential) => {
    setSelectedCredential(credential)
    setFormDialogOpen(true)
  }, [])

  /**
   * 删除按钮点击处理
   * Requirements: 5.16
   */
  const handleDeleteClick = useCallback((credential: AccountCredential) => {
    setSelectedCredential(credential)
    setDeleteDialogOpen(true)
  }, [])

  /**
   * 确认删除处理
   * Requirements: 5.17
   */
  const handleConfirmDelete = useCallback(() => {
    if (!selectedCredential) return

    deleteCredential.mutate(selectedCredential.id, {
      onSuccess: () => {
        toast.success('凭证删除成功')
        setDeleteDialogOpen(false)
        setSelectedCredential(undefined)
      },
      onError: (error) => {
        const errorMessage =
          error instanceof Error ? error.message : '删除失败，请重试'
        toast.error(errorMessage)
      },
    })
  }, [selectedCredential, deleteCredential])

  /**
   * 取消删除处理
   */
  const handleCancelDelete = useCallback(() => {
    setDeleteDialogOpen(false)
    setSelectedCredential(undefined)
  }, [])

  /**
   * 表单对话框状态变更处理
   */
  const handleFormDialogOpenChange = useCallback((open: boolean) => {
    setFormDialogOpen(open)
    if (!open) {
      setSelectedCredential(undefined)
    }
  }, [])

  /**
   * 获取律师显示名称
   */
  const getLawyerDisplayName = useCallback(
    (lawyer: { id: number; real_name: string; username: string }) => {
      return lawyer.real_name || lawyer.username || `律师 ${lawyer.id}`
    },
    []
  )

  // ========== 渲染 ==========
  return (
    <div className="flex flex-col gap-4">
      {/* 顶部操作栏 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        {/* 律师筛选 - Requirements: 5.3 */}
        <div className="w-full sm:w-[200px]">
          <Select
            value={lawyerId?.toString() ?? ALL_LAWYERS_VALUE}
            onValueChange={handleLawyerFilterChange}
            disabled={isLoadingLawyers}
          >
            <SelectTrigger className="h-10 w-full">
              <SelectValue
                placeholder={isLoadingLawyers ? '加载中...' : '选择律师'}
              />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL_LAWYERS_VALUE}>全部律师</SelectItem>
              {(lawyers ?? []).map((lawyer) => (
                <SelectItem key={lawyer.id} value={lawyer.id.toString()}>
                  {getLawyerDisplayName(lawyer)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {/* 新建按钮 - Requirements: 5.4 */}
        <Button onClick={handleCreateClick} className="w-full sm:w-auto">
          <Plus className="mr-2 size-4" />
          新建凭证
        </Button>
      </div>

      {/* 表格 */}
      <CredentialTable
        credentials={credentials ?? []}
        lawyers={lawyers ?? []}
        isLoading={isLoadingCredentials}
        onEdit={handleEditClick}
        onDelete={handleDeleteClick}
      />

      {/* 表单对话框 - Requirements: 5.4 */}
      <CredentialFormDialog
        open={formDialogOpen}
        onOpenChange={handleFormDialogOpenChange}
        credential={selectedCredential}
      />

      {/* 删除确认对话框 - Requirements: 5.16, 5.17 */}
      <AlertDialog open={deleteDialogOpen} onOpenChange={setDeleteDialogOpen}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <div className="bg-destructive/10 text-destructive mx-auto mb-4 flex size-12 items-center justify-center rounded-full">
              <Trash2 className="size-6" />
            </div>
            <AlertDialogTitle className="text-center">
              确认删除凭证
            </AlertDialogTitle>
            <AlertDialogDescription className="text-center">
              您确定要删除凭证「{selectedCredential?.site_name}」吗？此操作无法撤销。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter className="sm:justify-center">
            <AlertDialogCancel
              onClick={handleCancelDelete}
              disabled={deleteCredential.isPending}
            >
              取消
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={handleConfirmDelete}
              disabled={deleteCredential.isPending}
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
            >
              {deleteCredential.isPending ? '删除中...' : '确认删除'}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  )
}

export default CredentialList
