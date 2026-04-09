/**
 * Reminder Utility Functions
 * 提醒工具函数
 *
 * @module features/reminders/utils
 */

import { differenceInDays, startOfDay } from 'date-fns'
import type { Reminder, ReminderFilters, ReminderStatus } from './types'

// ============================================================================
// 状态计算
// ============================================================================

/**
 * 计算提醒状态
 *
 * 根据到期时间计算提醒的状态：
 * - overdue: 已逾期（due_at 已过期）
 * - upcoming: 即将到期（7天内到期，包含今天）
 * - normal: 正常（超过7天）
 *
 * @param dueAt - 到期时间（ISO datetime 字符串或 null）
 * @returns 提醒状态
 *
 * @example
 * ```ts
 * getReminderStatus(null) // 'normal'
 * getReminderStatus('2020-01-01T00:00:00Z') // 'overdue' (过去的日期)
 * getReminderStatus(new Date(Date.now() + 3 * 24 * 60 * 60 * 1000).toISOString()) // 'upcoming' (3天后)
 * getReminderStatus(new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString()) // 'normal' (30天后)
 * ```
 *
 * **Validates: Requirements 2.1, 2.2, 2.3**
 */
export function getReminderStatus(dueAt: string | null): ReminderStatus {
  if (!dueAt) return 'normal'

  const now = new Date()
  const dueDate = new Date(dueAt)

  // 检查是否已逾期（到期时间在当前时间之前）
  if (dueDate < now) return 'overdue'

  // 计算从今天开始到到期日的天数差
  // 使用 startOfDay 确保比较的是日期而非精确时间
  const diffDays = differenceInDays(startOfDay(dueDate), startOfDay(now))

  // 7天内到期（包含今天，即 diffDays <= 7）
  if (diffDays <= 7) return 'upcoming'

  return 'normal'
}

// ============================================================================
// 状态样式
// ============================================================================

/**
 * 状态样式映射
 *
 * 为每种提醒状态定义对应的 Tailwind CSS 类名，
 * 支持明亮和暗夜两种主题模式。
 *
 * - overdue: 红色背景和边框
 * - upcoming: 琥珀色/黄色背景和边框
 * - normal: 无特殊样式
 */
export const STATUS_STYLES: Record<ReminderStatus, string> = {
  overdue: 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800',
  upcoming: 'bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800',
  normal: '',
}

/**
 * 获取提醒状态对应的样式类名
 *
 * @param status - 提醒状态
 * @returns Tailwind CSS 类名字符串
 *
 * @example
 * ```ts
 * getStatusStyles('overdue') // 'bg-red-50 dark:bg-red-950/20 border-red-200 dark:border-red-800'
 * getStatusStyles('upcoming') // 'bg-amber-50 dark:bg-amber-950/20 border-amber-200 dark:border-amber-800'
 * getStatusStyles('normal') // ''
 * ```
 *
 * **Validates: Requirements 2.1, 2.2, 2.3, 2.4**
 */
export function getStatusStyles(status: ReminderStatus): string {
  return STATUS_STYLES[status]
}

/**
 * 根据到期时间直接获取样式类名
 *
 * 这是一个便捷函数，结合了 getReminderStatus 和 getStatusStyles。
 *
 * @param dueAt - 到期时间（ISO datetime 字符串或 null）
 * @returns Tailwind CSS 类名字符串
 *
 * @example
 * ```ts
 * getStatusStylesFromDueAt('2020-01-01T00:00:00Z') // 红色样式（已逾期）
 * getStatusStylesFromDueAt(null) // '' （无到期时间）
 * ```
 */
export function getStatusStylesFromDueAt(dueAt: string | null): string {
  return getStatusStyles(getReminderStatus(dueAt))
}

// ============================================================================
// 筛选函数
// ============================================================================

/**
 * 筛选提醒列表
 *
 * 根据筛选条件过滤提醒列表，支持：
 * - 按类型筛选：只返回指定类型的提醒
 * - 按日期范围筛选：只返回到期时间在指定范围内的提醒（包含边界）
 * - 组合筛选：同时满足类型和日期范围条件
 *
 * @param reminders - 提醒列表
 * @param filters - 筛选条件
 * @returns 筛选后的提醒列表
 *
 * @example
 * ```ts
 * // 按类型筛选
 * filterReminders(reminders, { reminderType: 'hearing' })
 *
 * // 按日期范围筛选
 * filterReminders(reminders, {
 *   dateFrom: new Date('2024-01-01'),
 *   dateTo: new Date('2024-12-31')
 * })
 *
 * // 组合筛选
 * filterReminders(reminders, {
 *   reminderType: 'hearing',
 *   dateFrom: new Date('2024-01-01'),
 *   dateTo: new Date('2024-12-31')
 * })
 * ```
 *
 * **Validates: Requirements 3.1, 3.2, 3.4**
 */
export function filterReminders(
  reminders: Reminder[],
  filters: ReminderFilters
): Reminder[] {
  const { reminderType, dateFrom, dateTo } = filters

  return reminders.filter((reminder) => {
    // 按类型筛选
    if (reminderType !== undefined && reminder.reminder_type !== reminderType) {
      return false
    }

    // 按日期范围筛选（需要 due_at 存在）
    if (dateFrom !== undefined || dateTo !== undefined) {
      // 如果没有到期时间，则不符合日期范围筛选条件
      if (!reminder.due_at) {
        return false
      }

      const dueDate = startOfDay(new Date(reminder.due_at))

      // 检查起始日期（包含）
      if (dateFrom !== undefined) {
        const fromDate = startOfDay(dateFrom)
        if (dueDate < fromDate) {
          return false
        }
      }

      // 检查结束日期（包含）
      if (dateTo !== undefined) {
        const toDate = startOfDay(dateTo)
        if (dueDate > toDate) {
          return false
        }
      }
    }

    return true
  })
}
