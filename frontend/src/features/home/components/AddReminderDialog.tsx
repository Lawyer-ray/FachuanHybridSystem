import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { toast } from 'sonner'

import { createReminder, listReminderTypes, searchTargetOptions, type TargetOption } from '../api'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { formatCN, parseKey } from '../domain'
import { cn } from '@/lib/utils'

/** 关联对象分类 tab。'all' = 全部 */
const TABS: { key: string; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'contract', label: '合同' },
  { key: 'case', label: '案件' },
  { key: 'case_log', label: '日志' },
]

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
  // 关联对象：kw=输入框文本，picked=已选中的候选（null 表示未选）
  const [kw, setKw] = useState('')
  const [options, setOptions] = useState<TargetOption[]>([])
  const [picked, setPicked] = useState<TargetOption | null>(null)
  const [searching, setSearching] = useState(false)
  // 候选分类筛选：'all' / contract / case / case_log
  const [tab, setTab] = useState('all')

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
      setKw('')
      setOptions([])
      setPicked(null)
      setSearching(false)
      setTab('all')
    }
  }, [day, defaultTime])

  // 关键字联想：输入停止 300ms 后打接口（避开逐字符请求）
  const debounce = useRef(0)
  useEffect(() => {
    const q = kw.trim()
    window.clearTimeout(debounce.current)
    if (!q || picked) {
      setOptions([])
      return
    }
    debounce.current = window.setTimeout(async () => {
      setSearching(true)
      try {
        setOptions(await searchTargetOptions(q))
      } catch {
        setOptions([])
      } finally {
        setSearching(false)
      }
    }, 300)
    return () => window.clearTimeout(debounce.current)
  }, [kw, picked])

  // 当前 tab 下可见的候选
  const visibleOptions = useMemo(
    () => (tab === 'all' ? options : options.filter((o) => o.target_type === tab)),
    [options, tab],
  )

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
      const msg =
        e && typeof e === 'object' && 'data' in e
          ? ((e as { data?: { message?: string } }).data?.message ?? '')
          : ''
      toast.error(msg || '新增失败，请稍后重试')
      setBusy(false)
    }
  }

  return (
    <Dialog open={day != null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-[380px]">
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

          {/* 关联对象：可选。不绑的话 admin 日历里会显示成"独立提醒" */}
          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[12px] font-medium">关联案件 / 合同</span>
              {picked && (
                <button
                  type="button"
                  className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
                  onClick={() => {
                    setPicked(null)
                    setKw('')
                  }}
                >
                  <X className="h-3 w-3" />
                  清除
                </button>
              )}
            </div>
            {picked ? (
              <div className="flex h-9 items-center gap-2 rounded-[8px] border border-input bg-secondary/40 px-2.5">
                <span className="flex-none rounded bg-secondary px-1.5 py-[1px] text-[10px] font-semibold text-secondary-foreground">
                  {picked.target_type_label}
                </span>
                <span className="min-w-0 flex-1 truncate text-[12.5px]">{picked.title}</span>
              </div>
            ) : (
              <div className="relative">
                <input
                  className="h-9 w-full rounded-[8px] border border-input bg-background px-2.5 text-[12.5px] outline-none focus:border-ring/40"
                  value={kw}
                  onChange={(e) => setKw(e.target.value)}
                  placeholder={searching ? '搜索中…' : '输入当事人名称 / 案号搜索'}
                />

                {options.length > 0 && (
                  <>
                    {/* 兜底层：点别处收起候选 */}
                    <div className="fixed inset-0 z-40" onClick={() => setOptions([])} aria-hidden />
                    {/* 候选面板**向上**展开：输入框在弹窗中部，向下会顶出视口。
                        自身限高可滚，不把弹窗撑高。 */}
                    <div className="absolute inset-x-0 bottom-[calc(100%+4px)] z-50 max-h-[228px] overflow-hidden rounded-[10px] border border-border bg-card shadow-[0_10px_28px_rgba(0,0,0,.14)]">
                      {/* 分类筛选 tab：合同 / 案件 / 案件日志，点一下只看这类 */}
                      <div className="flex items-center gap-1 border-b border-border px-1.5 py-1.5">
                        {TABS.filter((t) => t.key === 'all' || options.some((o) => o.target_type === t.key)).map(
                          (t) => {
                            const n = t.key === 'all' ? options.length : options.filter((o) => o.target_type === t.key).length
                            return (
                              <button
                                key={t.key}
                                type="button"
                                onClick={() => setTab(t.key)}
                                className={cn(
                                  'flex-none rounded-[6px] px-2 py-[3px] text-[11px] font-medium transition-colors',
                                  tab === t.key
                                    ? 'bg-foreground text-background'
                                    : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
                                )}
                              >
                                {t.label}
                                <span className="ml-1 tabular-nums opacity-60">{n}</span>
                              </button>
                            )
                          },
                        )}
                      </div>
                      {/* 结果列表 */}
                      <div className="max-h-[184px] overflow-y-auto py-1">
                        {visibleOptions.map((o) => (
                          <button
                            key={`${o.target_type}-${o.id}`}
                            type="button"
                            className="flex w-full items-center gap-2 px-2.5 py-[7px] text-left transition-colors hover:bg-secondary"
                            onClick={() => {
                              setPicked(o)
                              setKw('')
                              setOptions([])
                            }}
                          >
                            <span className="flex-none rounded bg-secondary px-1.5 py-[1px] text-[10px] font-semibold text-secondary-foreground">
                              {o.target_type_label}
                            </span>
                            <span className="min-w-0 flex-1 truncate text-[12px]">{o.title}</span>
                            {o.hint && (
                              <span className="max-w-[110px] flex-none truncate text-[10px] text-muted-foreground">
                                {o.hint}
                              </span>
                            )}
                          </button>
                        ))}
                      </div>
                    </div>
                  </>
                )}

                {kw.trim() && !searching && options.length === 0 && (
                  <p className="mt-1 text-[10.5px] text-muted-foreground">没有匹配的关联对象，也可以留空不绑定</p>
                )}
              </div>
            )}
          </div>

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
            保存
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
