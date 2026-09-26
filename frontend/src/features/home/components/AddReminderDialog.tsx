import { useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { createReminder, listReminderTypes } from '../api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { formatCN, parseKey } from '../domain'

interface Props {
  /** 目标日期 YYYY-MM-DD；null 表示关闭 */
  day: string | null
  /** 默认时刻 HH:mm（点空白处时取当前时间，点已有事件的时刻则沿用） */
  defaultTime: string
  onClose: () => void
  onSaved: () => void
}

/**
 * 新增安排弹窗（点日历空白格打开）。
 *
 * 只收集后端必填的三项：类型 + 内容 + 时间。关联案件/合同不做——那需要
 * 一个带检索的选择器，放在这个高频入口里太重；要挂案子的话在 admin 的
 * 提醒日历里建更合适。
 */
export function AddReminderDialog({ day, defaultTime, onClose, onSaved }: Props) {
  const [type, setType] = useState('other')
  const [content, setContent] = useState('')
  const [time, setTime] = useState(defaultTime)
  const [busy, setBusy] = useState(false)

  const { data: types = [] } = useQuery({
    queryKey: ['reminder-types'],
    queryFn: listReminderTypes,
    staleTime: 10 * 60_000,
  })

  // 每次打开都重置表单（否则上次填的内容会留着）
  useEffect(() => {
    if (day) {
      setType('other')
      setContent('')
      setTime(defaultTime)
      setBusy(false)
    }
  }, [day, defaultTime])

  const trimmed = content.trim()
  const canSave = trimmed.length > 0 && /^\d{2}:\d{2}$/.test(time) && !busy

  const submit = async () => {
    if (!day || !canSave) return
    setBusy(true)
    try {
      await createReminder({
        reminder_type: type,
        content: trimmed,
        // 后端要 date-time；本地时间拼接后不带时区，Django 按当前时区解释
        due_at: `${day}T${time}:00`,
      })
      toast.success(`已添加到 ${formatCN(parseKey(day))} ${time}`)
      onSaved()
      onClose()
    } catch (e) {
      const msg =
        e && typeof e === 'object' && 'data' in e
          ? ((e as { data?: { message?: string } }).data?.message ?? '')
          : ''
      toast.error(msg || '新增失败，请稍后重试')
      setBusy(false)
    }
  }

  const labelFor = useMemo(() => types.find((t) => t.value === type)?.label ?? '其他', [types, type])

  return (
    <Dialog open={day != null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[380px]">
        <DialogHeader>
          <DialogTitle className="text-[15px]">新增安排</DialogTitle>
          <p className="mt-0.5 text-[12px] text-muted-foreground">
            {day ? `${formatCN(parseKey(day))} ${time}` : ''}
          </p>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium">类型</span>
            <select
              className="h-9 rounded-[8px] border border-input bg-background px-2.5 text-[12.5px] outline-none focus:border-ring/40"
              value={type}
              onChange={(e) => setType(e.target.value)}
            >
              {types.length === 0 && <option value="other">其他</option>}
              {types.map((t) => (
                <option key={t.value} value={t.value}>
                  {t.label}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium">内容</span>
            <input
              className="h-9 rounded-[8px] border border-input bg-background px-2.5 text-[12.5px] outline-none focus:border-ring/40"
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

          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium">时刻</span>
            <input
              className="h-9 rounded-[8px] border border-input bg-background px-2.5 text-[12.5px] tabular-nums outline-none focus:border-ring/40"
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value)}
            />
          </label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={busy}>
            取消
          </Button>
          <Button onClick={() => void submit()} disabled={!canSave}>
            {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
            保存（{labelFor}）
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
