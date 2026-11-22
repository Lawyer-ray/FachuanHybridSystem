import { useEffect, useId, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, X } from 'lucide-react'
import { toast } from 'sonner'

import { createReminder, listReminderTypes, REMINDER_TYPES_KEY, type TargetOption } from '../api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { formatCN, parseKey } from '../domain'
import { TargetPicker } from './TargetPicker'
import { errMessage } from '@/lib/errors'

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
 * 收集：类型 + 内容 + 时刻（后端必填三项），外加**关联对象**（可选）。
 *
 * 关联对象很关键：不绑定的提醒在 admin 日历里会显示成"独立提醒"，
 * 也拿不到案件名当标题——等于白建。所以这里做了个轻量的关键字联想
 * 输入框（打关键字 → 调 /reminders/target-options 出候选 → 选中即绑定），
 * 和 admin 提醒日历里那套交互一致，只是做成了弹窗内的紧凑版。
 *
 * 后端 ReminderIn 的 contract_id / case_id / case_log_id 三者最多绑一个
 * （模型 CheckConstraint），所以选中一个就够，不做多选。
 */
export function AddReminderDialog({ day, defaultTime, onClose, onSaved }: Props) {
  const [type, setType] = useState('other')
  const [content, setContent] = useState('')
  const [time, setTime] = useState(defaultTime)
  const [busy, setBusy] = useState(false)
  // combobox ARIA 挂点：aria-controls / label htmlFor 都指向候选列表与输入框，
  // 用 useId 防止未来同弹窗多实例时 id 撞车
  const targetInputId = useId()
  const targetListId = useId()
  // 关联对象：picked=已选中的候选（null 表示未选，此时展示检索框）
  const [picked, setPicked] = useState<TargetOption | null>(null)

  const { data: types = [] } = useQuery({
    queryKey: REMINDER_TYPES_KEY,
    queryFn: listReminderTypes,
    staleTime: 10 * 60_000,
  })

  // 每次打开都重置表单（否则上次填的内容会留着）。
  // 关联检索框内部的词/tab/面板状态由 TargetPicker 以 key={day} 重挂时自己复位
  useEffect(() => {
    if (day) {
      setType('other')
      setContent('')
      setTime(defaultTime)
      setBusy(false)
      setPicked(null)
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
        target_type: picked?.target_type ?? null,
        target_id: picked?.id ?? null,
      })
      toast.success(
        `已添加到 ${formatCN(parseKey(day))} ${time}${picked ? ` · ${picked.target_type_label}：${picked.title}` : ''}`,
      )
      onSaved()
      onClose()
    } catch (e) {
      toast.error(errMessage(e, '新增失败，请稍后重试'))
      setBusy(false)
    }
  }

  return (
    <Dialog open={day != null} onOpenChange={(open) => !open && onClose()}>
      {/* grid-cols-[minmax(0,1fr)]：DialogContent 是单列 auto grid，auto 轨道的
          min 是内容 min-content。关联对象选中态那行是不可断行的长合同名
          （truncate = nowrap），会把列撑到远超 380px，整块内容横向溢出、
          右侧控件与「保存」按钮被推出视口。minmax(0,…) 把列 min 钳到 0，
          内层 min-w-0 + truncate 才真正生效（同 PaymentDialog 的修法）。
          max-h + overflow-y-auto：内容多/视口矮时内部滚动，不让底部按钮被顶出。*/}
      <DialogContent className="grid-cols-[minmax(0,1fr)] max-h-[calc(100%-2rem)] overflow-y-auto sm:max-w-[380px]">
        <DialogHeader>
          <DialogTitle className="text-[15px]">新增安排</DialogTitle>
          <DialogDescription className="mt-0.5 text-[12px] text-muted-foreground">
            {day ? `${formatCN(parseKey(day))} ${time}` : ''}
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium">类型</span>
            <select
              className="h-9 w-full rounded-[8px] border border-input bg-background px-2.5 text-[12.5px] outline-none focus:border-ring/40"
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

          {/* 关联对象：可选。不绑的话 admin 日历里会显示成"独立提醒" */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              {/* htmlFor 关联下方检索输入框（同「类型」字段的写法）；选中态展示行
                  没有可聚焦控件，此时 label 指向未挂载的输入框，无副作用 */}
              <label htmlFor={targetInputId} className="text-[12px] font-medium">
                关联案件 / 合同
              </label>
              {picked && (
                <button
                  type="button"
                  className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                  onClick={() => setPicked(null)}
                >
                  <X className="h-3 w-3" />
                  清除
                </button>
              )}
            </div>
            {picked && (
              <div className="flex h-9 items-center gap-2 rounded-[8px] border border-input bg-secondary/40 px-2.5">
                <span className="flex-none rounded bg-secondary px-1.5 py-[1px] text-[10px] font-semibold text-secondary-foreground">
                  {picked.target_type_label}
                </span>
                <span className="min-w-0 flex-1 truncate text-[12.5px]">{picked.title}</span>
              </div>
            )}
            {/* 检索框常驻挂载（picked 时 open=false 自行不渲染）：保留 tab 选择等内部态，
                让「清除」后重新展开时跟以前一样接着上次的分类筛选 */}
            <TargetPicker
              key={day ?? 'none'}
              open={!picked}
              inputId={targetInputId}
              listId={targetListId}
              onPick={setPicked}
            />
          </div>

          <label className="flex flex-col gap-1.5">
            <span className="text-[12px] font-medium">内容</span>
            <input
              className="h-9 w-full rounded-[8px] border border-input bg-background px-2.5 text-[12.5px] outline-none focus:border-ring/40"
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
              className="h-9 w-full rounded-[8px] border border-input bg-background px-2.5 text-[12.5px] tabular-nums outline-none focus:border-ring/40"
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
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
