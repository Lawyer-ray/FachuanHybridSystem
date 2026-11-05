import { useId, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Loader2, X } from 'lucide-react'
import { toast } from 'sonner'

import { listReminderTypes, REMINDER_TYPES_KEY, searchTargetOptions, updateReminder } from '../api'
import type { CalendarEvent, TargetOption, TargetType } from '../api'
import { useTypeaheadSearch } from '@/hooks/use-typeahead-search'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

/** 关联对象分类 tab（与新增弹窗同构：'all' = 全部） */
const TARGET_TABS: { key: string; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'contract', label: '合同' },
  { key: 'case', label: '案件' },
  { key: 'case_log', label: '日志' },
]

/**
 * 关联对象的**待提交变更**，三态（见 api/reminders.ts 的 UpdateReminderIn）：
 *   - pick：换绑到候选对象
 *   - clear：解除绑定
 * 不做任何操作时保持 `null`，提交时不含任何关联字段 → 后端保持原绑定。
 */
type TargetChange = { kind: 'pick'; option: TargetOption } | { kind: 'clear' } | null

/** 提交时带上 target_type/target_id 或 clear_target；没动过关联就什么都不带 */
function targetPayload(change: TargetChange) {
  if (!change) return {}
  return change.kind === 'pick'
    ? { target_type: change.option.target_type, target_id: change.option.id }
    : { clear_target: true }
}

/** 保存成功 toast：把改过的关联对象写在后面，让用户一眼确认真的换绑了 */
function savedMessage(change: TargetChange): string {
  if (change?.kind === 'pick') return `已保存 · ${change.option.target_type_label}：${change.option.title}`
  if (change?.kind === 'clear') return '已保存 · 已解除关联'
  return '已保存'
}

/**
 * 事件的 target_type → { 收窄后的类型, 中文标签 }。
 *
 * 生成物把该字段声明为裸 string；后端 `_target_of` 给的是**中文标签**
 * （「合同」「案件」「案件日志」，见 calendar_view_service.py），不是枚举码。
 * 两种写法都收，未知值一律当未关联（回显宁可留空，也不猜错绑定）。
 */
function echoTargetType(raw: string): { type: TargetType; label: string } | null {
  switch (raw) {
    case 'contract':
    case '合同':
      return { type: 'contract', label: '合同' }
    case 'case':
    case '案件':
      return { type: 'case', label: '案件' }
    case 'case_log':
    case '案件日志':
      return { type: 'case_log', label: '案件日志' }
    default:
      return null
  }
}

interface Props {
  event: CalendarEvent
  /** 保存成功（父层负责 invalidate 日历 + 关弹窗） */
  onSaved: () => void
  onCancel: () => void
}

/**
 * 日历事件的编辑表单（EventDetailDialog 的编辑态，点「编辑」原地切换）。
 *
 * 收集：类型 / 内容 / 日期 / 时刻，外加**关联对象**（合同 / 案件 / 案件日志三选一）。
 * 关联对象这一项是补救入口：日历上「未关联案件」的事件原本没有任何地方能补绑，
 * 只能删了重建。交互复用新增弹窗那套（关键字联想 → /reminders/target-options →
 * 选中即绑定），后台接口与 admin 提醒日历同源。
 *
 * 提交走 PUT /reminders/{id}（后端 exclude_unset 部分更新）：
 *   - 关联对象没动 → 请求体不含任何关联字段，原绑定保留
 *   - 换了 / 新绑 → 拆成 contract_id / case_id / case_log_id 之一
 *   - 点了「解除关联」→ 三个字段显式发 null
 * 合并事件（同一庭审多条同步记录）后端给 can_edit=false，进不来这里。
 */
export function EventEditForm({ event, onSaved, onCancel }: Props) {
  const [type, setType] = useState(event.reminder_type || 'other')
  const [content, setContent] = useState(event.content)
  const [day, setDay] = useState(event.day)
  const [time, setTime] = useState(event.time)
  const [busy, setBusy] = useState(false)
  // combobox ARIA 挂点（同 AddReminderDialog：useId 防多实例 id 撞车）
  const targetInputId = useId()
  const targetListId = useId()
  // target = 当前回显的绑定（来自事件本身，换绑后同步成候选名）；
  // change = 本次编辑对关联对象的待提交变更（pick / clear / 未动）
  const [target, setTarget] = useState<{ type: TargetType; name: string } | null>(() => {
    const echo = echoTargetType(event.target_type)
    return echo ? { type: echo.type, name: event.target_name } : null
  })
  const [change, setChange] = useState<TargetChange>(null)
  const [optionsHidden, setOptionsHidden] = useState(false)
  const [tab, setTab] = useState('all')
  // 选/解绑后收起检索框，改回展示行；点「修改」再展开
  const [picking, setPicking] = useState(false)

  const { data: types = [] } = useQuery({
    queryKey: REMINDER_TYPES_KEY,
    queryFn: listReminderTypes,
    staleTime: 10 * 60_000,
  })

  // 关键字联想：只在展开检索框且手上没有候选变更时发请求（与新增弹窗同参数口径）
  const {
    keyword: kw,
    setKeyword: setKw,
    data: searched = [],
    isSearching: searching,
  } = useTypeaheadSearch<TargetOption[]>({
    queryKey: (dk) => ['reminder-target-options', dk],
    queryFn: ({ keyword, signal }) => searchTargetOptions(keyword, signal),
    enabled: picking,
  })
  const options = useMemo(
    () => (picking && !optionsHidden ? searched : []),
    [picking, optionsHidden, searched],
  )
  const visibleOptions = useMemo(
    () => (tab === 'all' ? options : options.filter((o) => o.target_type === tab)),
    [options, tab],
  )

  // 展示行（非检索态）的三个展示量。未绑定时两栏都退回「未关联」，不留空白
  const bound = target !== null || change !== null
  const typeLabel =
    change?.kind === 'pick'
      ? change.option.target_type_label
      : (target && echoTargetType(target.type)?.label) || '未关联'
  const nameLabel =
    change?.kind === 'pick'
      ? change.option.title
      : change?.kind === 'clear'
        ? '保存后解除绑定'
        : (target?.name ?? '未关联')

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
        ...targetPayload(change),
      })
      toast.success(savedMessage(change))
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

      {/* 关联对象：可换绑 / 解除，也可在未绑定时补绑（原「未关联案件」的补救入口） */}
      <div className={fieldLabel}>
        <div className="flex items-center justify-between">
          <label htmlFor={targetInputId} className={labelText}>
            关联对象
          </label>
          {/* 未动过关联对象时才给「修改 / 选择」入口：已换绑或有待解除时由下面的展示行接管 */}
          {!picking && change === null && (
            <button
              type="button"
              className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => {
                setPicking(true)
                setKw('')
              }}
            >
              {target ? '修改' : '选择'}
            </button>
          )}
          {!picking && change?.kind === 'clear' && <span className="text-[11px] text-muted-foreground">保存后解除</span>}
          {!picking && change?.kind === 'pick' && (
            <button
              type="button"
              className="flex items-center gap-1 text-[11px] text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => {
                setChange(null)
                setKw('')
              }}
            >
              <X className="h-3 w-3" />
              撤销
            </button>
          )}
        </div>
        {!picking ? (
          <div className={`${fieldInput} flex items-center gap-2`}>
            <span className="flex-none rounded bg-secondary px-1.5 py-[1px] text-[10px] font-semibold text-secondary-foreground">
              {typeLabel}
            </span>
            <span className={cn('min-w-0 flex-1 truncate', !bound && 'text-muted-foreground')}>{nameLabel}</span>
            {bound && (
              <button
                type="button"
                aria-label="解除关联"
                className="flex-none rounded p-0.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
                onClick={() => {
                  setChange({ kind: 'clear' })
                  setTarget(null)
                  setPicking(false)
                  setKw('')
                }}
              >
                <X className="h-3 w-3" />
              </button>
            )}
          </div>
        ) : (
          <div className="relative">
            {/* combobox 语义同 AddReminderDialog：候选来自后端联想 */}
            <input
              id={targetInputId}
              role="combobox"
              aria-expanded={options.length > 0}
              aria-controls={targetListId}
              aria-autocomplete="list"
              className={fieldInput}
              value={kw}
              onChange={(e) => {
                setOptionsHidden(false)
                setKw(e.target.value)
              }}
              placeholder={searching ? '搜索中…' : '输入当事人名称 / 案号搜索'}
            />

            {options.length > 0 && (
              <>
                <div className="fixed inset-0 z-40" onClick={() => setOptionsHidden(true)} aria-hidden />
                {/* 候选面板向上展开：输入框在表单中下部，向下会顶出弹窗。
                    自身限高可滚，不把表单撑高 */}
                <div className="absolute inset-x-0 bottom-[calc(100%+4px)] z-50 max-h-[228px] overflow-hidden rounded-[10px] border border-border bg-card shadow-[0_10px_28px_rgba(0,0,0,.14)]">
                  <div className="flex items-center gap-1 border-b border-border px-1.5 py-1.5">
                    {TARGET_TABS.filter((t) => t.key === 'all' || options.some((o) => o.target_type === t.key)).map(
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
                  <div
                    id={targetListId}
                    role="listbox"
                    aria-label="关联对象候选"
                    className="max-h-[184px] overflow-y-auto py-1"
                  >
                    {visibleOptions.map((o) => (
                      <button
                        key={`${o.target_type}-${o.id}`}
                        type="button"
                        role="option"
                        aria-selected={false}
                        className="flex w-full items-center gap-2 px-2.5 py-[7px] text-left transition-colors hover:bg-secondary"
                        onClick={() => {
                          setChange({ kind: 'pick', option: o })
                          setTarget({ type: o.target_type, name: o.title })
                          setPicking(false)
                          setKw('')
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
