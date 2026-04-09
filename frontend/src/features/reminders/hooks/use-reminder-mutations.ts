/**
 * useReminderMutations Hook
 * 重要日期提醒增删改 mutations hook
 *
 * 使用 TanStack Query 实现提醒的创建、更新、删除操作
 * 配置缓存失效策略，确保数据一致性
 *
 * Requirements: 4.2, 5.2, 6.2
 */

import { useMutation, useQueryClient, type UseMutationResult } from '@tanstack/react-query'

import { reminderApi } from '../api'
import type { Reminder, ReminderInput } from '../types'
import { reminderQueryKey } from './use-reminders'

// ============================================================================
// Types
// ============================================================================

/**
 * 更新提醒参数接口
 */
export interface UpdateReminderParams {
  /** 提醒 ID */
  id: number
  /** 更新的提醒数据 */
  data: ReminderInput
}

/**
 * useReminderMutations 返回值接口
 */
export interface UseReminderMutationsReturn {
  /** 创建提醒 mutation */
  createMutation: UseMutationResult<Reminder, Error, ReminderInput>
  /** 更新提醒 mutation */
  updateMutation: UseMutationResult<Reminder, Error, UpdateReminderParams>
  /** 删除提醒 mutation */
  deleteMutation: UseMutationResult<void, Error, number>
}

// ============================================================================
// Hook
// ============================================================================

/**
 * 提醒增删改 Mutations Hook
 *
 * 提供创建、更新、删除提醒的 mutation 操作，
 * 并在操作成功后自动失效相关缓存以刷新列表。
 *
 * @returns 包含 createMutation、updateMutation、deleteMutation 三个 mutation 的对象
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { createMutation, updateMutation, deleteMutation } = useReminderMutations()
 *
 * // 创建提醒
 * createMutation.mutate({
 *   reminder_type: 'hearing',
 *   content: '开庭提醒',
 *   due_at: '2024-03-15T09:00:00Z',
 *   contract_id: 123,
 * }, {
 *   onSuccess: (reminder) => {
 *     toast.success('创建成功')
 *   },
 *   onError: (error) => {
 *     toast.error('创建失败')
 *   },
 * })
 *
 * // 更新提醒
 * updateMutation.mutate({
 *   id: 1,
 *   data: {
 *     reminder_type: 'hearing',
 *     content: '更新后的开庭提醒',
 *     due_at: '2024-03-20T10:00:00Z',
 *     contract_id: 123,
 *   },
 * })
 *
 * // 删除提醒
 * deleteMutation.mutate(1, {
 *   onSuccess: () => {
 *     toast.success('删除成功')
 *   },
 * })
 * ```
 *
 * Requirements: 4.2 (创建), 5.2 (更新), 6.2 (删除)
 */
export function useReminderMutations(): UseReminderMutationsReturn {
  const queryClient = useQueryClient()

  /**
   * 创建提醒 Mutation
   * POST /api/v1/reminders/
   *
   * Requirements: 4.2
   */
  const createMutation = useMutation<Reminder, Error, ReminderInput>({
    mutationFn: (data: ReminderInput) => reminderApi.create(data),
    onSuccess: () => {
      // 创建成功后，失效所有提醒列表缓存以刷新数据（包括不同筛选条件的缓存）
      queryClient.invalidateQueries({
        queryKey: ['reminders'],
      })
    },
  })

  /**
   * 更新提醒 Mutation
   * PUT /api/v1/reminders/{id}/
   *
   * Requirements: 5.2
   */
  const updateMutation = useMutation<Reminder, Error, UpdateReminderParams>({
    mutationFn: ({ id, data }: UpdateReminderParams) => reminderApi.update(id, data),
    onSuccess: (updatedReminder, { id }) => {
      // 更新成功后，失效所有提醒列表缓存和该提醒的详情缓存
      queryClient.invalidateQueries({
        queryKey: ['reminders'],
      })
      queryClient.invalidateQueries({
        queryKey: reminderQueryKey(id),
      })
      // 直接更新缓存中的数据，避免额外请求
      queryClient.setQueryData(reminderQueryKey(id), updatedReminder)
    },
  })

  /**
   * 删除提醒 Mutation
   * DELETE /api/v1/reminders/{id}/
   *
   * Requirements: 6.2
   */
  const deleteMutation = useMutation<void, Error, number>({
    mutationFn: (id: number) => reminderApi.delete(id),
    onSuccess: (_, id) => {
      // 删除成功后，失效所有提醒列表缓存
      queryClient.invalidateQueries({
        queryKey: ['reminders'],
      })
      // 移除该提醒的详情缓存
      queryClient.removeQueries({
        queryKey: reminderQueryKey(id),
      })
    },
  })

  return {
    createMutation,
    updateMutation,
    deleteMutation,
  }
}

export default useReminderMutations
