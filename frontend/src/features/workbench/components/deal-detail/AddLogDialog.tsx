import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { errMessage } from '@/lib/errors'

import { createCaseLog, listReminderTypes } from '../../api'

function plusDays(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() + n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

/**
 * 记日志（案件卡上的「＋ 记日志」）。
 *
 * 日志长在**案件**上——合同没有时间轴。所以从案件卡进来时归属已经定了；
 * 这一版不做「记到别的案子」，少一个选错的机会（要跨案记，去那张卡上点）。
 *
 * **「同时设一个期限」为什么必须有**：律师写「今天收到传票」时，下一句几乎总是
 * 「15 天内举证」。后端的 `POST /cases/logs` 本来就支持带 `reminder_type` +
 * `reminder_time` 一起建，分成两次操作反而容易漏掉那条期限。默认不勾选——
 * 多数日志只是留痕。
 */
export function AddLogDialog({
  open,
  caseId,
  caseLabel,
  onClose,
  onSaved,
}: {
  open: boolean
  caseId: number
  /** 案件程序名（标题里显示，让律师确认记在哪一案上） */
  caseLabel: string
  onClose: () => void
  onSaved: () => void
}) {
  const [content, setContent] = useState('')
  const [withReminder, setWithReminder] = useState(false)
  const [type, setType] = useState('')
  const [due, setDue] = useState(plusDays(3))
  const [time, setTime] = useState('09:00')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const { data: types = [] } = useQuery({
    queryKey: ['reminder-types'],
    queryFn: listReminderTypes,
    staleTime: 10 * 60_000,
    enabled: open && withReminder,
  })
  const effectiveType = type || types[0]?.value || 'other'

  const canSubmit =
    content.trim().length > 0 &&
    (!withReminder || (/^\d{4}-\d{2}-\d{2}$/.test(due) && /^\d{2}:\d{2}$/.test(time)))

  async function submit() {
    if (!canSubmit || busy) return
    setBusy(true)
    setError(null)
    try {
      await createCaseLog({
        caseId,
        content: content.trim(),
        ...(withReminder ? { reminderType: effectiveType, reminderTime: `${due}T${time}:00` } : {}),
      })
      toast.success(withReminder ? '已记日志并设好期限' : '已记日志')
      onSaved()
      onClose()
    } catch (e) {
      setError(errMessage(e, '记日志失败，请重试'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent className="sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>记日志</DialogTitle>
          <DialogDescription>
            记到「{caseLabel}」。日志按时间顺序长在该案的时间轴上，右栏期限不受影响，除非你在下面顺手约一个。
          </DialogDescription>
        </DialogHeader>

        <form
          className="flex flex-col gap-3 pt-1"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <label className="flex flex-col gap-1">
            <span className="text-[12px] font-[600] text-secondary-foreground">内容</span>
            <Textarea
              aria-label="日志内容"
              autoFocus
              value={content}
              placeholder="例：收到法院传票，定于 12 月 20 日 9:30 一审开庭 / 与对方电话沟通，同意分期"
              onChange={(e) => setContent(e.target.value)}
            />
            <span className="text-[11px] text-muted-foreground/80">
              链接可以直接粘（法院短信里的长 URL 会自动变成「查看链接」）；附件在列表里另传。
            </span>
          </label>

          <label className="flex items-center gap-2 text-[12.5px] text-secondary-foreground">
            <input
              type="checkbox"
              className="size-4 accent-foreground"
              checked={withReminder}
              onChange={(e) => setWithReminder(e.target.checked)}
            />
            同时设一个期限
          </label>

          {withReminder && (
            <div className="grid grid-cols-2 gap-3 max-[520px]:grid-cols-1">
              <label className="flex flex-col gap-1">
                <span className="text-[12px] font-[600] text-secondary-foreground">期限类型</span>
                <select
                  aria-label="期限类型"
                  className="h-9 w-full min-w-0 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
                  value={effectiveType}
                  onChange={(e) => setType(e.target.value)}
                >
                  {(types.length ? types : [{ value: 'other', label: '其他' }]).map((t) => (
                    <option key={t.value} value={t.value}>
                      {t.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-[12px] font-[600] text-secondary-foreground">到期</span>
                <span className="flex gap-1.5">
                  <Input type="date" aria-label="到期日期" value={due} onChange={(e) => setDue(e.target.value)} />
                  <Input
                    type="time"
                    aria-label="到期时间"
                    className="w-[104px] flex-none"
                    value={time}
                    onChange={(e) => setTime(e.target.value)}
                  />
                </span>
              </label>
            </div>
          )}

          {error && <p className="text-[12px] text-status-red">{error}</p>}

          <DialogFooter className="mt-1 gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              取消
            </Button>
            <Button type="submit" disabled={!canSubmit || busy}>
              {busy && <Loader2 className="mr-1 size-3.5 animate-spin" />}
              记下
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
