import { useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router'
import { FileText, Landmark, Mail, Paperclip, Search, Users } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { createApiClient } from '@/lib/api'
import { Dialog, DialogContent } from '@/components/ui/dialog'
import { cn } from '@/lib/utils'

/**
 * 全局检索（⌘K）。
 *
 * 后端已有现成接口：GET /api/v1/search?q=，跨 6 类实体并发搜索
 * （客户 / 案件 / 合同 / 收件箱 / 法院短信 / 联系人），每类最多 10 条。
 * 这里做命令面板：⌘K 唤起、输入即搜（防抖 250ms）、↑↓ 选、回车跳、
 * Esc 关。跳转目标只指向已存在的页面，未实现的类别点选后给明确提示。
 */

const searchApi = createApiClient({ prefix: '/api/v1/search' })

interface Hit {
  category: string
  id: number
  title: string
  subtitle: string
}

/** 空结果集：固定引用，避免每次渲染都是新数组导致下游 useMemo 抖动 */
const EMPTY_HITS: Hit[] = []

/**
 * 各类别 → 展示名 / 图标 / 点击后的去处。
 *
 * to 只对**已存在**的路由给出（目前只有 /material-prep/:id）。
 * 案件 / 客户 / 合同这些页还没做，若硬链过去会命中 App.tsx 的通配
 * 重定向、静默跳回首页——比明确说"还没做"更糟。所以它们不给 to，
 * 点选时由调用方弹提示。
 */
const CATEGORIES: Record<string, { label: string; icon: typeof Users; to?: (id: number) => string }> = {
  cases: { label: '案件', icon: FileText },
  clients: { label: '客户', icon: Users },
  contracts: { label: '合同', icon: FileText },
  inbox: { label: '收件箱', icon: Mail, to: (id) => `/material-prep/${id}` },
  court_sms: { label: '法院短信', icon: Landmark },
  contacts: { label: '联系人', icon: Paperclip },
}

const CATEGORY_ORDER = ['cases', 'clients', 'contracts', 'inbox', 'court_sms', 'contacts']

/** 输入防抖间隔（ms）：输入即搜，但请求攒一撮再发，避免每次按键都重排结果列表 */
const DEBOUNCE_MS = 250

async function runSearch(q: string): Promise<Hit[]> {
  const res = await searchApi.get('', { searchParams: { q, limit: 8 } }).json<Record<string, { id: number; title: string; subtitle: string }[]>>()
  const out: Hit[] = []
  for (const cat of CATEGORY_ORDER) {
    for (const it of res[cat] ?? []) {
      out.push({ category: cat, id: it.id, title: it.title, subtitle: it.subtitle })
    }
  }
  return out
}

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
  const [activeCat, setActiveCat] = useState('all')
  const inputRef = useRef<HTMLInputElement>(null)

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
  const [debounced, setDebounced] = useState(trimmed)
  useEffect(() => {
    if (trimmed === debounced) return
    const t = window.setTimeout(() => setDebounced(trimmed), DEBOUNCE_MS)
    return () => window.clearTimeout(t)
  }, [trimmed, debounced])

  const { data, isFetching } = useQuery({
    queryKey: ['global-search', debounced],
    queryFn: () => runSearch(debounced),
    enabled: open && debounced.length >= 1,
    staleTime: 30_000,
    // 保留上一次结果，别在换关键词时先清空再填充（少了这一下空白，就不闪）
    placeholderData: (prev) => prev,
  })

  // 当前是否"在检索"：输入框非空才算。
  // 删空关键词时不算检索——此时必须只显示引导文案，不能残留旧结果/旧标签，
  // 否则会出现「引导语 + 旧标签 + 旧结果」三份内容同时在场、高度反复横跳。
  const searching = trimmed.length > 0
  const hits = useMemo(() => (searching ? (data ?? EMPTY_HITS) : EMPTY_HITS), [data, searching])

  // 新结果回来 / 切换筛选时把光标移回第一项（跟着 debounced，不跟 trimmed）
  useEffect(() => setCursor(0), [debounced, activeCat])

  /** 每个类别的命中数（用于筛选标签上的计数，含全部） */
  const counts = useMemo(() => {
    const m = new Map<string, number>()
    for (const h of hits) m.set(h.category, (m.get(h.category) ?? 0) + 1)
    return m
  }, [hits])

  /** 按当前筛选过滤后的结果；↑↓ / Enter 都以它为准 */
  const flat = useMemo(
    () => (activeCat === 'all' ? hits : hits.filter((h) => h.category === activeCat)),
    [hits, activeCat],
  )

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
    const meta = CATEGORIES[hit.category]
    onOpenChange(false)
    if (!meta?.to) onPickUnavailable?.(meta?.label ?? hit.category)
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
        {/* 搜索框 */}
        <div className="flex items-center gap-2.5 border-b border-border px-4">
          <Search className="h-4 w-4 flex-none text-muted-foreground" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="搜案件 / 客户 / 合同 / 收件箱 / 法院短信 / 联系人"
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
          {!searching && (
            <div className="px-3 py-8 text-center text-[12.5px] text-muted-foreground">
              输入关键词开始搜索
            </div>
          )}
          {searching && flat.length === 0 && !isFetching && (
            <div className="px-3 py-8 text-center text-[12.5px] text-muted-foreground">
              没有匹配「{trimmed}」的结果
            </div>
          )}
          {CATEGORY_ORDER.filter((c) => groups.has(c)).map((cat) => {
            const meta = CATEGORIES[cat]
            const Icon = meta.icon
            const hits = groups.get(cat) ?? []
            return (
              <div key={cat} className="mb-1.5 last:mb-0">
                <div className="px-2 py-1 text-[10.5px] font-semibold text-muted-foreground">{meta.label}</div>
                {hits.map((h) => {
                  const idx = flat.indexOf(h)
                  const to = meta.to?.(h.id)
                  const Row = (
                    <>
                      <Icon className="h-3.5 w-3.5 flex-none text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate text-[12.5px]">{h.title}</span>
                      {h.subtitle && (
                        <span className="max-w-[140px] flex-none truncate text-[10.5px] text-muted-foreground">{h.subtitle}</span>
                      )}
                    </>
                  )
                  return to ? (
                    <Link
                      key={`${cat}-${h.id}`}
                      to={to}
                      onClick={() => onOpenChange(false)}
                      className={cn(
                        'flex w-full items-center gap-2.5 rounded-[7px] px-2 py-[7px] no-underline transition-colors',
                        idx === cursor ? 'bg-secondary text-foreground' : 'text-secondary-foreground hover:bg-secondary/60',
                      )}
                    >
                      {Row}
                    </Link>
                  ) : (
                    <button
                      key={`${cat}-${h.id}`}
                      type="button"
                      onClick={() => pick(h)}
                      className={cn(
                        'flex w-full items-center gap-2.5 rounded-[7px] px-2 py-[7px] text-left text-secondary-foreground transition-colors',
                        idx === cursor ? 'bg-secondary' : 'hover:bg-secondary/60',
                      )}
                    >
                      {Row}
                      <span className="flex-none text-[10px] text-muted-foreground">未建页</span>
                    </button>
                  )
                })}
              </div>
            )
          })}
        </div>

        {/* 底部快捷键提示 */}
        <div className="flex items-center gap-3 border-t border-border px-4 py-2 text-[10.5px] text-muted-foreground">
          <span>↑↓ 选择</span>
          <span>↵ 打开</span>
          <span>Esc 关闭</span>
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
