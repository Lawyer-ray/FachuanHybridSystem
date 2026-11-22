import { useEffect, useMemo, useState } from 'react'
import { useTypeaheadSearch } from '@/hooks/use-typeahead-search'
import { cn } from '@/lib/utils'

import { searchTargetOptions, type TargetOption } from '../api'

/** 关联对象分类 tab。'all' = 全部 */
const TARGET_TABS: { key: string; label: string }[] = [
  { key: 'all', label: '全部' },
  { key: 'contract', label: '合同' },
  { key: 'case', label: '案件' },
  { key: 'case_log', label: '日志' },
]

export interface TargetPickerProps {
  /** 检索是否展开：父层决定什么时候从「已选展示行 / 修改入口」切到检索框 */
  open: boolean
  /** 检索输入框 id（父层 label 的 htmlFor 指向它） */
  inputId: string
  /** 候选列表 id（输入框 aria-controls 指向它） */
  listId: string
  /** 选中候选：父层负责落到自己的状态（「已选」或「待提交变更」），关键词与面板由本组件收起 */
  onPick: (option: TargetOption) => void
}

/**
 * 关联对象关键字联想输入框（新增安排弹窗与事件编辑表单共用）。
 *
 * 打关键字 → 调 /reminders/target-options 出候选 → 点候选回给父层绑定。两侧
 * 逐字复制过一遍（含分类 tab 计数、向上展开的面板、兜底层、空结果提示），
 * 上一轮已因此出现过只改一边的漂移（`grid-cols-[minmax(0,1fr)]` 修法各贴一遍）。
 *
 * 只负责「检索 + 选一个候选」：选中之后怎么落状态（新增弹窗的 picked / 编辑
 * 表单的待提交变更 + 回显行）差异很大，留在各自弹窗里。
 */
export function TargetPicker({ open, inputId, listId, onPick }: TargetPickerProps) {
  // 关键字联想：输入停 250ms 才请求、空关键词不发（minLength 默认 1）、
  // 上一请求由 signal 自动中止（无响应竞态）。
  // searching 取 hook 的 isSearching（已扣掉 keepPreviousData 的 placeholder 帧），
  // 不能直接用 isFetching —— 后者恒真，输入框会一直显示「搜索中…」。
  const { keyword: kw, setKeyword: setKw, data: searched = [], isSearching: searching } = useTypeaheadSearch<TargetOption[]>({
    queryKey: (dk) => ['reminder-target-options', dk],
    queryFn: ({ keyword, signal }) => searchTargetOptions(keyword, signal),
    enabled: open,
  })
  // 点候选兜底层收起；重新输入即展开（对齐旧实现「点别处清空 options」）
  const [optionsHidden, setOptionsHidden] = useState(false)
  // 候选分类筛选：'all' / contract / case / case_log
  const [tab, setTab] = useState('all')

  // 收起时把检索词与面板状态复位：下次展开是干净的空输入框（不会带着上次没选中的词）
  useEffect(() => {
    if (!open) {
      setKw('')
      setOptionsHidden(false)
    }
    // setKw 来自 hook 内 useState，引用恒稳定，列进 deps 不影响触发时机
  }, [open, setKw])

  const options = useMemo(
    () => (open && !optionsHidden ? searched : []),
    [open, optionsHidden, searched],
  )
  const visibleOptions = useMemo(
    () => (tab === 'all' ? options : options.filter((o) => o.target_type === tab)),
    [options, tab],
  )

  if (!open) return null

  return (
    <div className="relative">
      {/* combobox ARIA：输入框声明 listbox 弹层（aria-expanded 随候选有无开合，
          aria-controls 指向下方列表）；候选来自后端联想，aria-autocomplete="list"。
          键盘上下键未实现，不加 aria-activedescendant——只做静态语义，不发明新交互 */}
      <input
        id={inputId}
        role="combobox"
        aria-expanded={options.length > 0}
        aria-controls={listId}
        aria-autocomplete="list"
        className="h-9 w-full rounded-[8px] border border-input bg-background px-2.5 text-[12.5px] outline-none focus:border-ring/40"
        value={kw}
        onChange={(e) => {
          // 重新输入即展开候选：这一下同时作废「点候选收起」与「点了兜底层」
          // 两种隐藏态，所以两处都必须在这里复位（不是多余的重复）
          setOptionsHidden(false)
          setKw(e.target.value)
        }}
        placeholder={searching ? '搜索中…' : '输入当事人名称 / 案号搜索'}
      />

      {options.length > 0 && (
        <>
          {/* 兜底层：点别处收起候选 */}
          <div className="fixed inset-0 z-40" onClick={() => setOptionsHidden(true)} aria-hidden />
          {/* 候选面板**向上**展开：输入框在弹窗/表单中下部，向下会顶出视口。
              自身限高可滚，不把外层撑高。 */}
          <div className="absolute inset-x-0 bottom-[calc(100%+4px)] z-50 max-h-[228px] overflow-hidden rounded-[10px] border border-border bg-card shadow-[0_10px_28px_rgba(0,0,0,.14)]">
            {/* 分类筛选 tab：合同 / 案件 / 案件日志，点一下只看这类 */}
            <div className="flex items-center gap-1 border-b border-border px-1.5 py-1.5">
              {TARGET_TABS.filter((t) => t.key === 'all' || options.some((o) => o.target_type === t.key)).map((t) => {
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
              })}
            </div>
            {/* 结果列表：listbox 只包结果行，上方的分类 tab 留在
                listbox 外（它们仍是普通按钮，混进来会破坏语义） */}
            <div id={listId} role="listbox" aria-label="关联对象候选" className="max-h-[184px] overflow-y-auto py-1">
              {visibleOptions.map((o) => (
                <button
                  key={`${o.target_type}-${o.id}`}
                  type="button"
                  role="option"
                  aria-selected={false}
                  className="flex w-full items-center gap-2 px-2.5 py-[7px] text-left transition-colors hover:bg-secondary"
                  onClick={() => {
                    setKw('')
                    setOptionsHidden(false)
                    onPick(o)
                  }}
                >
                  <span className="flex-none rounded bg-secondary px-1.5 py-[1px] text-[10px] font-semibold text-secondary-foreground">
                    {o.target_type_label}
                  </span>
                  <span className="min-w-0 flex-1 truncate text-[12px]">{o.title}</span>
                  {o.hint && (
                    <span className="max-w-[110px] flex-none truncate text-[10px] text-muted-foreground">{o.hint}</span>
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
  )
}
