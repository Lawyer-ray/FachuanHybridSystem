/**
 * useReminders Hooks
 * 重要日期提醒查询 hooks
 *
 * 使用 TanStack Query 实现提醒列表和类型列表查询
 *
 * Requirements: 1.1, 1.2
 */

import { useQuery } from '@tanstack/react-query'

import { reminderApi } from '../api'
import type { Reminder, ReminderFilters, ReminderTypeOption } from '../types'

// ============================================================================
// Query Keys
// ============================================================================

/**
 * 提醒列表查询 Query Key
 *
 * @param filters - 筛选条件（可选）
 * @returns Query key 数组
 */
export const remindersQueryKey = (filters?: ReminderFilters) =>
  [
    'reminders',
    {
      reminderType: filters?.reminderType ?? null,
      dateFrom: filters?.dateFrom?.toISOString() ?? null,
      dateTo: filters?.dateTo?.toISOString() ?? null,
    },
  ] as const

/**
 * 单个提醒查询 Query Key
 *
 * @param id - 提醒 ID
 * @returns Query key 数组
 */
export const reminderQueryKey = (id: number) => ['reminder', id] as const

/**
 * 提醒类型列表 Query Key
 */
export const reminderTypesQueryKey = () => ['reminder-types'] as const

// ============================================================================
// Hooks
// ============================================================================

/**
 * 提醒列表查询 Hook
 *
 * @param filters - 筛选条件（可选）
 * @returns TanStack Query 结果，包含提醒列表
 *
 * @example
 * ```tsx
 * // 基础用法 - 获取所有提醒
 * const { data: reminders, isLoading, error } = useReminders()
 *
 * // 带筛选条件
 * const { data: reminders } = useReminders({
 *   reminderType: 'hearing',
 *   dateFrom: new Date('2024-01-01'),
 *   dateTo: new Date('2024-12-31'),
 * })
 * ```
 *
 * Requirements: 1.1 (展示提醒列表), 1.2 (加载状态)
 */
export function useReminders(filters?: ReminderFilters) {
  return useQuery<Reminder[]>({
    queryKey: remindersQueryKey(filters),
    queryFn: async () => {
      // 从 API 获取所有提醒
      // 注意：后端 API 支持 contract_id 和 case_log_id 筛选
      // 前端筛选（类型、日期范围）在获取数据后进行
      const reminders = await reminderApi.list()
      return reminders
    },
    // 5 分钟内数据视为新鲜，不会自动重新获取
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * 单个提醒查询 Hook
 *
 * @param id - 提醒 ID
 * @returns TanStack Query 结果，包含提醒详情
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { data: reminder, isLoading, error } = useReminder(123)
 *
 * // 在详情页中使用
 * function ReminderDetailPage() {
 *   const { id } = useParams<{ id: string }>()
 *   const { data: reminder, isLoading, error } = useReminder(Number(id))
 *
 *   if (isLoading) return <Loading />
 *   if (error) return <Error error={error} />
 *   if (!reminder) return <NotFound />
 *
 *   return <ReminderDetail reminder={reminder} />
 * }
 * ```
 *
 * Requirements: 1.1
 */
export function useReminder(id: number) {
  return useQuery<Reminder>({
    queryKey: reminderQueryKey(id),
    queryFn: () => reminderApi.get(id),
    // 只有当 id 存在且有效时才启用查询
    enabled: !!id && id > 0,
    // 5 分钟内数据视为新鲜，不会自动重新获取
    staleTime: 5 * 60 * 1000,
  })
}

/**
 * 提醒类型列表查询 Hook
 *
 * @returns TanStack Query 结果，包含提醒类型选项列表
 *
 * @example
 * ```tsx
 * // 基础用法
 * const { data: types, isLoading } = useReminderTypes()
 *
 * // 在筛选组件中使用
 * function ReminderFilters() {
 *   const { data: types = [] } = useReminderTypes()
 *
 *   return (
 *     <Select>
 *       {types.map((type) => (
 *         <SelectItem key={type.value} value={type.value}>
 *           {type.label}
 *         </SelectItem>
 *       ))}
 *     </Select>
 *   )
 * }
 * ```
 *
 * Requirements: 1.1, 1.2
 */
export function useReminderTypes() {
  return useQuery<ReminderTypeOption[]>({
    queryKey: reminderTypesQueryKey(),
    queryFn: () => reminderApi.getTypes(),
    // 类型列表很少变化，设置较长的缓存时间
    staleTime: 30 * 60 * 1000, // 30 分钟
  })
}

export default useReminders
