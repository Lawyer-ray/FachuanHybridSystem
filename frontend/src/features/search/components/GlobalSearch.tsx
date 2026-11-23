import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router'
import { Search } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { EmptyBlock } from '@/components/shared/AsyncState'
import { useDebouncedValue } from '@/hooks/use-debounced-value'
import { cn } from '@/lib/utils'
import { CATEGORY_ORDER, runSearch } from '../api'
import { CATEGORIES, DEBOUNCE_MS, GLOBAL_SEARCH_KEY } from '../categories'
import { orderProjectHits } from '../domain'
import type { CategoryKey, Hit } from '../types'
import { HitRow } from './HitRow'
import { ProjectHits } from './ProjectHits'

/**
 * 全局检索（⌘K）。
 *
 * 命令面板：⌘K 唤起、输入即搜（防抖 250ms）、↑↓ 选、回车跳、
 * Esc 关。跳转目标只指向已存在的页面，未实现的类别点选后给明确提示。
 */

/** 空结果集：固定引用，避免每次渲染都是新数组导致下游 useMemo 抖动 */
const EMPTY_HITS: Hit[] = []

/** 两类引导态文案的排版：只覆盖间距与字号，居中/灰色由 EmptyBlock 定 */
const HINT_CLS = 'px-3 py-8 text-[12.5px]'

export function GlobalSearch({
  open,
  onOpenChange,
  onPickUnavailable,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  /** 点到还没建详情页的类别时触发（给 toast 提示） */
  onPickUnavailable?: (label: string) => void
}) {
  const [q, setQ] = useState('')
  const [cursor, setCursor] = useState(0)
  // 当前筛选类别：'all' = 全部；否则为 CATEGORY_ORDER 里的某个 category key
  const [activeCat, setActiveCat] = useState<'all' | CategoryKey>('all')
  const inputRef = useRef<HTMLInputElement>(null)
  const navigate = useNavigate()

  // 打开时聚焦输入框，关闭时清空（下次打开是干净的）
  useEffect(() => {
    if (open) {
      const t = window.setTimeout(() => inputRef.current?.focus(), 30)
      return () => window.clearTimeout(t)
    }
    setQ('')
    setCursor(0)
    setActiveCat('all')
  }, [open])

  const trimmed = q.trim()
  // 输入防抖：输入框即时响应，但请求延迟 DEBOUNCE_MS 触发。
  // 否则每敲一个字就发一次请求，结果列表反复涨落导致弹窗高度/内容不停跳（"闪烁"）。
  const debounced = useDebouncedValue(trimmed, DEBOUNCE_MS)

  const { data, isFetching } = useQuery({
    queryKey: [GLOBAL_SEARCH_KEY, debounced],
    queryFn: () => runSearch(debounced),
    enabled: open && debounced.length >= 1,
    staleTime: 30_000,
    // 保留上一次结果，别在换关键词时先清空再填充（少了这一下空白，就不闪）
    placeholderData: (prev) => prev,
  })

  // 是否"在检索"，以及当前该显示哪批结果，都跟 debounced（已用于请求的那个词）
  // 保持一致，不能跟 trimmed：trimmed 输入即变，data 还是上一个词的结果，
  // 两者错开就会闪（新关键词 + 旧结果同时在场）。
  // 删空关键词时同样只显示引导文案，不残留旧结果/旧标签。
  const searching = debounced.length > 0
  // 不包 useMemo：两个操作数本身就是常量（EMPTY_HITS 固定引用）或 react-query 的
  // 稳定 data 引用，memo 只多一层依赖比较，起不到省渲染的作用
  const hits = searching ? (data ?? EMPTY_HITS) : EMPTY_HITS

  // 新结果回来 / 切换筛选时把光标移回第一项（跟着 debounced，不跟 trimmed）
  useEffect(() => setCursor(0), [debounced, activeCat])

  /** 每个类别的命中数（用于筛选标签上的计数，含全部） */
  const counts = useMemo(() => {
    const m = new Map<string, number>()
    for (const h of hits) m.set(h.category, (m.get(h.category) ?? 0) + 1)
    return m
  }, [hits])

  /** 按当前筛选过滤后的结果；↑↓ / Enter 都以它为准。
   *  projects 段重排成「组头行 → 案件行」的视觉顺序（合同命中在前、其案件紧随），
   *  键盘光标序与分组渲染序一致；其余类别保持后端顺序垫后。 */
  const flat = useMemo(() => {
    const base = activeCat === 'all' ? hits : hits.filter((h) => h.category === activeCat)
    return activeCat === 'projects' || activeCat === 'all' ? orderProjectHits(base) : base
  }, [hits, activeCat])

  const groups = useMemo(() => {
    const m = new Map<string, Hit[]>()
    for (const h of flat) {
      const list = m.get(h.category)
      if (list) list.push(h)
      else m.set(h.category, [h])
    }
    return m
  }, [flat])

  const pick = (hit: Hit) => {
    // 后端 category 与前端注册表可能不同步（后端新增类别前端还没配），查不到按未实现处理
    const meta = CATEGORIES[hit.category as CategoryKey]
    onOpenChange(false)
    const to = meta?.to?.(hit)
    // 已建页的类别：无论鼠标点还是键盘回车都真正跳转（此前键盘回车只关面板不跳）
    if (to) {
      void navigate(to)
      return
    }
    onPickUnavailable?.(meta?.label ?? hit.category)
  }

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setCursor((c) => (flat.length ? (c + 1) % flat.length : 0))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setCursor((c) => (flat.length ? (c - 1 + flat.length) % flat.length : 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      const hit = flat[cursor]
      if (hit) pick(hit)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      {/* 宽度：只在 sm(≥640px) 以上放宽到 880px，小屏保持基类的 max-w-[calc(100%-2rem)]
          留边距。若写成无限定的 max-w-[880px]，会覆盖掉窄屏的留边规则导致横向溢出 */}
      <DialogContent
        className="top-[14%] translate-y-0 gap-0 p-0 sm:max-w-[880px]"
        showCloseButton={false}
      >
        {/* 可访问名称：命令面板无可见标题，给屏幕阅读器一个 DialogTitle */}
        <DialogTitle className="sr-only">全局检索</DialogTitle>
        {/* 搜索框 */}
        <div className="flex items-center gap-2.5 border-b border-border px-4">
          <Search className="h-4 w-4 flex-none text-muted-foreground" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="搜项目 / 当事人 / 收件箱 / 法院短信 / 联系人"
            className="h-12 flex-1 border-none bg-transparent text-[13.5px] outline-none placeholder:text-muted-foreground"
          />
          {/* 常驻占位不塌陷：若用 {isFetching && ...} 条件渲染，出现/消失会把输入框宽度
              挤来挤去，打字时观感就是"闪" */}
          <span
            className={cn(
              'flex-none text-[11px] transition-opacity',
              isFetching ? 'opacity-100' : 'pointer-events-none opacity-0',
            )}
            aria-hidden={!isFetching}
          >
            搜索中…
          </span>
          <kbd className="flex-none rounded border border-input bg-secondary px-1.5 py-0.5 text-[10px] text-muted-foreground">
            Esc
          </kbd>
        </div>

        {/* 筛选标签：有多少类命中才显示哪些 + 固定「全部」，纯前端过滤（后端一次已返回全部类别） */}
        {hits.length > 0 && (
          <div className="flex items-center gap-1.5 overflow-x-auto border-b border-border px-3 py-2">
            <FilterTab
              label="全部"
              count={hits.length}
              active={activeCat === 'all'}
              onClick={() => setActiveCat('all')}
            />
            {CATEGORY_ORDER.filter((c) => (counts.get(c) ?? 0) > 0).map((cat) => (
              <FilterTab
                key={cat}
                label={CATEGORIES[cat].label}
                count={counts.get(cat) ?? 0}
                active={activeCat === cat}
                onClick={() => setActiveCat(cat)}
              />
            ))}
          </div>
        )}

        {/* 结果 */}
        <div className="max-h-[52vh] overflow-y-auto px-2 py-2">
          {!searching && <EmptyBlock className={HINT_CLS}>输入关键词开始搜索</EmptyBlock>}
          {searching && flat.length === 0 && !isFetching && (
            <EmptyBlock className={HINT_CLS}>没有匹配「{trimmed}」的结果</EmptyBlock>
          )}
          {CATEGORY_ORDER.filter((c) => groups.has(c)).map((cat) => {
            const meta = CATEGORIES[cat]
            const catHits = groups.get(cat) ?? []
            // projects 单独走分组渲染（合同作组头、案件挂其下），与其余平铺类别不同构
            if (cat === 'projects') {
              return (
                <ProjectHits
                  key={cat}
                  hits={catHits}
                  flat={flat}
                  cursor={cursor}
                  onOpenChange={onOpenChange}
                  pick={pick}
                />
              )
            }
            return (
              <div key={cat} className="mb-1.5 last:mb-0">
                <div className="px-2 py-1 text-[10.5px] font-semibold text-muted-foreground">{meta.label}</div>
                {catHits.map((h) => (
                  <HitRow
                    key={`${cat}-${h.id}`}
                    hit={h}
                    category={meta}
                    to={meta.to?.(h)}
                    active={flat.indexOf(h) === cursor}
                    onOpenChange={onOpenChange}
                    onPick={pick}
                  />
                ))}
              </div>
            )
          })}
        </div>

        {/* 底部快捷键提示 */}
        <div className="flex items-center gap-3 border-t border-border px-4 py-2 text-[10.5px] text-muted-foreground">
          <span>↑↓ 选择</span>
          <span>↵ 打开</span>
          <span>Esc 关</span>
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** 筛选标签：类名 + 命中数；选中态用高亮底 */
function FilterTab({
  label,
  count,
  active,
  onClick,
}: {
  label: string
  count: number
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'flex flex-none items-center gap-1 rounded-full border px-2.5 py-[3px] text-[11.5px] whitespace-nowrap transition-colors',
        active
          ? 'border-transparent bg-foreground font-medium text-background'
          : 'border-border text-secondary-foreground hover:bg-secondary',
      )}
    >
      {label}
      <span className={cn('tabular-nums', active ? 'opacity-70' : 'text-muted-foreground')}>{count}</span>
    </button>
  )
}
