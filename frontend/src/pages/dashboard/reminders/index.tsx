/**
 * Reminders Page
 * 重要日期提醒管理页面
 *
 * @module pages/dashboard/reminders
 *
 * Requirements: 1.1 - 用户访问 /admin/reminders 页面展示提醒列表
 */

import { CalendarClock } from 'lucide-react'

import { ReminderList } from '@/features/reminders'

/**
 * 提醒管理页面
 *
 * 组装 ReminderList 组件，设置页面标题
 */
export default function RemindersPage() {
  return (
    <div className="space-y-6">
      {/* 页面标题 */}
      <div className="flex items-center gap-3">
        <div className="rounded-lg bg-primary/10 p-2">
          <CalendarClock className="size-6 text-primary" />
        </div>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">重要日期提醒</h1>
          <p className="text-muted-foreground">
            管理案件和合同的重要时间节点提醒
          </p>
        </div>
      </div>

      {/* 提醒列表 */}
      <ReminderList />
    </div>
  )
}
