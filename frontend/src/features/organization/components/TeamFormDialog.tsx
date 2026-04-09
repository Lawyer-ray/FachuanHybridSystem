/**
 * TeamFormDialog Component
 *
 * 团队表单对话框组件
 * - 实现表单字段（团队名称、团队类型、所属律所）
 * - 使用 React Hook Form + Zod 验证
 * - 支持创建和编辑模式
 * - 编辑模式下预填充现有数据
 * - 保存成功后关闭对话框
 * - 显示成功/失败提示
 *
 * Requirements:
 * - 4.4: 提供表单编辑团队信息
 * - 4.8: 表单包含字段：团队名称（必填）、团队类型（必填）、所属律所（必填）
 * - 4.9: 对必填字段进行验证
 * - 4.10: 用户点击「保存」按钮且表单验证通过时，保存数据并显示成功提示
 * - 4.11: 保存成功后关闭对话框
 * - 4.12: 用户点击「取消」按钮时关闭对话框
 * - 4.13: 编辑模式下预填充现有数据
 * - 4.14: 保存失败时显示错误信息
 */

import { useEffect, useCallback } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import { Loader2, Save, X } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  Form,
  FormField,
  FormItem,
  FormLabel,
  FormControl,
  FormMessage,
} from '@/components/ui/form'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'

import { useTeamMutations } from '../hooks/use-team-mutations'
import { useLawFirms } from '../hooks/use-lawfirms'
import type { Team, TeamType } from '../types'
import { TEAM_TYPE_LABELS } from '../types'

// ============================================================================
// Types
// ============================================================================

/**
 * TeamFormDialog 组件属性
 */
export interface TeamFormDialogProps {
  /** 对话框打开状态 */
  open: boolean
  /** 对话框状态变更回调 */
  onOpenChange: (open: boolean) => void
  /** 编辑模式下的团队数据（如果提供则为编辑模式，否则为创建模式） */
  team?: Team
}

// ============================================================================
// Zod Validation Schema
// ============================================================================

/**
 * 团队表单验证 Schema
 *
 * Requirements:
 * - 4.8: 表单包含字段：团队名称（必填）、团队类型（必填）、所属律所（必填）
 * - 4.9: 对必填字段进行验证
 */
const teamTypeValues = ['lawyer', 'biz'] as const

const teamFormSchema = z.object({
  name: z.string().min(1, '团队名称不能为空'),
  team_type: z.enum(teamTypeValues, { message: '请选择团队类型' }),
  law_firm_id: z.number({ message: '请选择所属律所' }).min(1, '请选择所属律所'),
})

type TeamFormData = z.infer<typeof teamFormSchema>

// ============================================================================
// Main Component
// ============================================================================

/**
 * 团队表单对话框组件
 *
 * 提供以下功能：
 * - 封装 Dialog + Form
 * - 处理创建和编辑两种模式
 * - 成功时关闭对话框并显示成功提示
 * - 失败时显示错误提示并保留表单数据
 *
 * Requirements: 4.4, 4.8, 4.9, 4.10, 4.11, 4.12, 4.13, 4.14
 */
export function TeamFormDialog({
  open,
  onOpenChange,
  team,
}: TeamFormDialogProps) {
  const isEditMode = !!team

  // ========== Data Fetching ==========

  // 获取律所列表用于下拉选择
  const { data: lawFirms = [], isLoading: isLoadingLawFirms } = useLawFirms()

  // 获取 mutations
  const { createTeam, updateTeam } = useTeamMutations()

  const isPending = createTeam.isPending || updateTeam.isPending

  // ========== Form Setup ==========

  // 初始化表单，使用 Zod schema 进行验证 - Requirements: 4.9
  const form = useForm<TeamFormData>({
    resolver: zodResolver(teamFormSchema),
    defaultValues: {
      name: '',
      team_type: undefined,
      law_firm_id: undefined,
    },
  })

  // ========== Effects ==========

  // 编辑模式下预填充现有数据 - Requirements: 4.13
  useEffect(() => {
    if (open) {
      if (isEditMode && team) {
        form.reset({
          name: team.name,
          team_type: team.team_type,
          law_firm_id: team.law_firm,
        })
      } else {
        // 创建模式下重置表单
        form.reset({
          name: '',
          team_type: undefined,
          law_firm_id: undefined,
        })
      }
    }
  }, [open, isEditMode, team, form])

  // ========== Event Handlers ==========

  /**
   * 表单提交处理
   * Requirements: 4.10, 4.11, 4.14
   */
  const onSubmit = useCallback(
    (data: TeamFormData) => {
      const submitData = {
        name: data.name,
        team_type: data.team_type as TeamType,
        law_firm_id: data.law_firm_id,
      }

      if (isEditMode && team) {
        // 更新团队
        updateTeam.mutate(
          { id: team.id, data: submitData },
          {
            onSuccess: () => {
              // Requirements: 4.10 - 显示成功提示
              toast.success('团队更新成功')
              // Requirements: 4.11 - 关闭对话框
              onOpenChange(false)
            },
            onError: (error) => {
              // Requirements: 4.14 - 显示错误信息
              const errorMessage =
                error instanceof Error ? error.message : '更新失败，请重试'
              toast.error(errorMessage)
              // 保留表单数据，不关闭对话框
            },
          }
        )
      } else {
        // 创建团队
        createTeam.mutate(submitData, {
          onSuccess: () => {
            // Requirements: 4.10 - 显示成功提示
            toast.success('团队创建成功')
            // Requirements: 4.11 - 关闭对话框
            onOpenChange(false)
          },
          onError: (error) => {
            // Requirements: 4.14 - 显示错误信息
            const errorMessage =
              error instanceof Error ? error.message : '创建失败，请重试'
            toast.error(errorMessage)
            // 保留表单数据，不关闭对话框
          },
        })
      }
    },
    [isEditMode, team, createTeam, updateTeam, onOpenChange]
  )

  /**
   * 取消按钮处理
   * Requirements: 4.12
   */
  const handleCancel = useCallback(() => {
    onOpenChange(false)
  }, [onOpenChange])

  // ========== Render ==========

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>
            {isEditMode ? '编辑团队' : '新建团队'}
          </DialogTitle>
          <DialogDescription>
            {isEditMode
              ? '修改团队信息，完成后点击保存'
              : '填写团队信息，创建新的团队'}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            {/* 团队名称字段 - Requirements: 4.8 (必填) */}
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    团队名称 <span className="text-destructive">*</span>
                  </FormLabel>
                  <FormControl>
                    <Input
                      placeholder="请输入团队名称"
                      disabled={isPending}
                      className="h-11"
                      {...field}
                    />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* 团队类型字段 - Requirements: 4.8 (必填) */}
            <FormField
              control={form.control}
              name="team_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    团队类型 <span className="text-destructive">*</span>
                  </FormLabel>
                  <Select
                    onValueChange={field.onChange}
                    value={field.value}
                    disabled={isPending}
                  >
                    <FormControl>
                      <SelectTrigger className="h-11 w-full">
                        <SelectValue placeholder="请选择团队类型" />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {(Object.keys(TEAM_TYPE_LABELS) as TeamType[]).map((type) => (
                        <SelectItem key={type} value={type}>
                          {TEAM_TYPE_LABELS[type]}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* 所属律所字段 - Requirements: 4.8 (必填) */}
            <FormField
              control={form.control}
              name="law_firm_id"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>
                    所属律所 <span className="text-destructive">*</span>
                  </FormLabel>
                  <Select
                    onValueChange={(value) => field.onChange(Number(value))}
                    value={field.value?.toString()}
                    disabled={isPending || isLoadingLawFirms}
                  >
                    <FormControl>
                      <SelectTrigger className="h-11 w-full">
                        <SelectValue placeholder={isLoadingLawFirms ? '加载中...' : '请选择所属律所'} />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      {lawFirms.map((lawFirm) => (
                        <SelectItem key={lawFirm.id} value={lawFirm.id.toString()}>
                          {lawFirm.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <FormMessage />
                </FormItem>
              )}
            />

            {/* 操作按钮 - Requirements: 4.10, 4.12 */}
            <DialogFooter className="pt-4">
              {/* 取消按钮 - Requirements: 4.12 */}
              <Button
                type="button"
                variant="outline"
                onClick={handleCancel}
                disabled={isPending}
                className="h-11"
              >
                <X className="mr-2 size-4" />
                取消
              </Button>

              {/* 保存按钮 - Requirements: 4.10 */}
              <Button type="submit" disabled={isPending} className="h-11">
                {isPending ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    保存中...
                  </>
                ) : (
                  <>
                    <Save className="mr-2 size-4" />
                    保存
                  </>
                )}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

// ============================================================================
// Default Export
// ============================================================================

export default TeamFormDialog
