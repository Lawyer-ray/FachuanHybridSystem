import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { listReminderTypes, REMINDER_TYPES_KEY, updateReminder } from '../api'
import type { CalendarEvent } from '../api'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

interface Props {
  event: CalendarEvent
  /** 保存成功（父层负责 invalidate 日历 + 关弹窗） */
  onSaved: () => void
  onCancel: () => void
}

/**
 * 日历事件的编辑表单（EventDetailDialog 的编辑态，点「编辑」原地切换）。
 *
 * 只收四项：类型 / 内容 / 日期 / 时刻——日历上改日程就是改这四样；
 * 关联对象（合同/案件绑定）不在此改，提交走 PUT /reminders/{id}
 * （后端 exclude_unset 部分更新，绑定原样保留）。
 * 合并事件（同一庭审多条同步记录）后端给 can_edit=false，进不来这里。
 */
export function EventEditForm({ event, onSaved, onCancel }: Props) {
  const [type, setType] = useState(event.reminder_type || 'other')
  const [content, setContent] = useState(event.content)
  const [day, setDay] = useState(event.day)
  const [time, setTime] = useState(event.time)
  const [busy, setBusy] = useState(false)

  const { data: types = [] } = useQuery({
    queryKey: REMINDER_TYPES_KEY,
    queryFn: listReminderTypes,
    staleTime: 10 * 60_000,
  })

  const trimmed = content.trim()
  const canSave = trimmed.length > 0 && /^\d{4}-\d{2}-\d{2}$/.test(day) && /^\d{2}:\d{2}$/.test(time) && !busy

  const submit = async () => {
    if (!canSave) return
    setBusy(true)
    try {
      await updateReminder(event.id, {
        reminder_type: type,
        content: trimmed,
        // 不带时区，Django 按当前时区解释（与新增弹窗同口径）
        due_at: `${day}T${time}:00`,
      })
      toast.success('已保存')
      onSaved()
    } catch (e) {
      toast.error(errMessage(e, '保存失败，请稍后重试'))
      setBusy(false)
    }
  }

  const fieldLabel = 'flex flex-col gap-1.5'
  const labelText = 'text-[12px] font-medium'
  const fieldInput =
    'h-9 w-full rounded-[8px] border border-input bg-background px-2.5 text-[12.5px] outline-none focus:border-ring/40'

  return (
    <div className="flex flex-col gap-3 px-5 py-4">
      <label className={fieldLabel}>
        <span className={labelText}>类型</span>
        <select className={fieldInput} value={type} onChange={(e) => setType(e.target.value)}>
          {/* 存量数据的类型可能不在最新枚举里，补一个原值 option 防止 select 静默归零 */}
          {!types.some((t) => t.value === type) && <option value={type}>{type}</option>}
          {types.map((t) => (
            <option key={t.value} value={t.value}>
              {t.label}
            </option>
          ))}
        </select>
      </label>

      <label className={fieldLabel}>
        <span className={labelText}>内容</span>
        <input
          className={fieldInput}
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && canSave) void submit()
          }}
          placeholder="例如：提交证据目录 / 和对方律师碰头"
          maxLength={255}
          autoFocus
        />
      </label>

      <div className="flex gap-2">
        <label className={cn(fieldLabel, 'min-w-0 flex-1')}>
          <span className={labelText}>日期</span>
          <input className={`${fieldInput} tabular-nums`} type="date" value={day} onChange={(e) => setDay(e.target.value)} />
        </label>
        <label className={cn(fieldLabel, 'min-w-0 flex-1')}>
          <span className={labelText}>时刻</span>
          <input
            className={`${fieldInput} tabular-nums`}
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
          />
        </label>
      </div>

      <div className="flex justify-end gap-2 pt-1">
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="flex h-9 items-center justify-center rounded-[8px] border border-border bg-card px-4 text-[12.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50"
        >
          取消
        </button>
        <button
          type="button"
          onClick={() => void submit()}
          disabled={!canSave}
          className="flex h-9 items-center justify-center gap-1.5 rounded-[8px] bg-foreground px-4 text-[12.5px] font-semibold text-background transition-opacity hover:opacity-85 disabled:cursor-not-allowed disabled:opacity-45"
        >
          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          保存
        </button>
      </div>
    </div>
  )
}
