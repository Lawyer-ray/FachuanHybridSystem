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
import { errMessage } from '@/lib/errors'

import { createReminder, listReminderTypes } from '../../api'

/** 本地「今天 + n 天」的 YYYY-MM-DD（不用 toISOString：那是 UTC，晚上会跳到明天） */
function plusDays(n: number): string {
  const d = new Date()
  d.setDate(d.getDate() + n)
  const mm = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${mm}-${dd}`
}

/**
 * 新增期限（右栏「期限」节的「＋ 新增」）。
 *
 * 为什么归属要选「委托 / 案件」：后端的提醒三选一绑定（contract / case / case_log），
 * 挂委托的是「合同层面的约定」（服务期、付款节点），挂案件的是「这个程序里的动作」
 * （开庭、举证、上诉期）。混着挂会在时间轴上出现「属于哪个案子看不出」的孤儿提醒。
 *
 * 表单刻意只问四件事：挂哪、什么类型、写什么、什么时候到期。类型来自
 * `GET /reminders/types`（后端唯一真源），不在这里硬编码中文。
 */
export function AddDeadlineDialog({
  open,
  contractId,
  cases,
  defaultCaseId = null,
  onClose,
  onSaved,
}: {
  open: boolean
  contractId: number
  /** 该合同下的案件（选「挂到案件」时用；没有案件就只留「委托」） */
  cases: Array<{ id: number; proc: string }>
  defaultCaseId?: number | null
  onClose: () => void
  onSaved: () => void
}) {
  const { data: types = [] } = useQuery({
    queryKey: ['reminder-types'],
    queryFn: listReminderTypes,
    staleTime: 10 * 60_000,
    enabled: open,
  })

  const [scope, setScope] = useState<'contract' | 'case'>(defaultCaseId != null ? 'case' : 'contract')
  const [caseId, setCaseId] = useState<number | null>(defaultCaseId ?? cases[0]?.id ?? null)
  const [type, setType] = useState('')
  const [content, setContent] = useState('')
  const [due, setDue] = useState(plusDays(1))
  const [time, setTime] = useState('09:00')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const effectiveType = type || types[0]?.value || 'other'
  const canSubmit = content.trim().length > 0 && /^\d{4}-\d{2}-\d{2}$/.test(due) && /^\d{2}:\d{2}$/.test(time)

  async function submit() {
    if (!canSubmit || busy) return
    setBusy(true)
    setError(null)
    try {
      await createReminder({
        reminderType: effectiveType,
        content: content.trim(),
        dueAt: `${due}T${time}:00`,
        ...(scope === 'case' && caseId != null ? { caseId } : { contractId }),
      })
      toast.success('已新增期限')
      onSaved()
      onClose()
    } catch (e) {
      // 停在原地、不清空输入：校验失败时重填一遍最招人烦
      setError(errMessage(e, '新增期限失败，请重试'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => !v && !busy && onClose()}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>新增期限</DialogTitle>
          <DialogDescription>到期后会出现在右栏「期限」与首页日历；今天到期标红。</DialogDescription>
        </DialogHeader>

        <form
          className="flex flex-col gap-3 pt-1"
          onSubmit={(e) => {
            e.preventDefault()
            void submit()
          }}
        >
          <label className="flex flex-col gap-1">
            <span className="text-[12px] font-[600] text-secondary-foreground">挂在哪</span>
            <div className="flex gap-2">
              <select
                aria-label="期限归属"
                className="h-9 min-w-0 flex-1 rounded-md border border-input bg-transparent px-2 text-sm outline-none focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
                value={scope === 'case' && caseId != null ? `case:${caseId}` : 'contract'}
                onChange={(e) => {
                  const v = e.target.value
                  if (v === 'contract') setScope('contract')
                  else {
                    setScope('case')
                    setCaseId(Number(v.slice(5)))
                  }
                }}
              >
                <option value="contract">整个委托（合同层面）</option>
                {cases.map((c) => (
                  <option key={c.id} value={`case:${c.id}`}>
                    {c.proc}（案件）
                  </option>
                ))}
              </select>
            </div>
          </label>

          <div className="grid grid-cols-2 gap-3 max-[520px]:grid-cols-1">
            <label className="flex flex-col gap-1">
              <span className="text-[12px] font-[600] text-secondary-foreground">类型</span>
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
                <Input
                  type="date"
                  aria-label="到期日期"
                  value={due}
                  onChange={(e) => setDue(e.target.value)}
                />
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

          <label className="flex flex-col gap-1">
            <span className="text-[12px] font-[600] text-secondary-foreground">内容</span>
            <Input
              aria-label="期限内容"
              value={content}
              maxLength={255}
              placeholder="例：一审开庭 / 举证期限届满 / 上诉期届满"
              onChange={(e) => setContent(e.target.value)}
            />
          </label>

          {error && <p className="text-[12px] text-status-red">{error}</p>}

          <DialogFooter className="mt-1 gap-2">
            <Button type="button" variant="outline" onClick={onClose} disabled={busy}>
              取消
            </Button>
            <Button type="submit" disabled={!canSubmit || busy}>
              {busy && <Loader2 className="mr-1 size-3.5 animate-spin" />}
              新增
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
