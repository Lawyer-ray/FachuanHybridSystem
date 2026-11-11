import { useEffect, useRef, type ReactNode } from 'react'
import { LayoutGrid, List, Loader2, Search } from 'lucide-react'
import { toast } from 'sonner'

import { cn } from '@/lib/utils'
import { INBOX_SOURCE_TABS } from '../inbox/constants'
import { useSyncSources } from '../inbox/hooks/use-sync-sources'
import { SyncButton } from '../inbox/components/SyncButton'
import type { DeskToolbarHandlers, DeskToolbarSlots, DeskViewMode } from './desk-toolbar-types'
import type { InboxSourceFilter } from '../inbox/types'
import type { PrepStage } from '../stages'

/**
 * 预处理页的**统一工具栏**：四个阶段共用这一条，各阶段只声明自己用哪些槽位。
 *
 * ═══ 为什么上提到这里，而不是各阶段各造一条 ═══
 * 以前只有收件箱阶段有筛选条（来源药丸 / 未读 / 搜索 / 同步），材料包阶段完全
 * 没有——同一个页面的两个阶段长得像两个页面。现在工具栏由 DeskPage 渲染，
 * 槽位由 `toolbarSlotsFor(stage)` 决定（契约见 desk-toolbar-types.ts），
 * 阶段切换时工具栏本身不消失，只是槽位变化，视觉上仍是同一页。
 *
 * ═══ 为什么同步状态机与它的提示都在这里 ═══
 * 同步是**通过工具栏发起的动作**：按钮作用于当前选中的来源档位，而档位选中态
 * 就住在工具栏的 handlers 里。状态机（轮询到完成、窗口天数回显）只依赖 `source`
 * 一个入参，本地创建即可，不必把 SyncResult 一路透传。
 *
 * 完成提示也必须跟着状态机走：状态机埋在哪，`idle + newCount` 这个跃迁就发生在哪。
 * 以前状态机在收件箱列表里，提示也在那里；按钮上提到工具栏后如果提示留在原处，
 * 转发的那份状态机永远 idle，这条提示就静默丢了。
 *
 * 收件箱的列表主体（InboxList）**不再**渲染筛选条——它只负责消息列表；
 * 筛选一律走这里，避免同一条筛选出现两份、两份状态各自漂移。
 */
export function DeskToolbar({
  stage,
  slots,
  handlers,
}: {
  stage: PrepStage
  slots: DeskToolbarSlots
  handlers: DeskToolbarHandlers
}) {
  // hook 必须无条件调用（档位切到材料包时同步按钮不渲染，但状态机不能被条件调用）；
  // 非收件箱阶段也不显示同步按钮，后端不会因此被额外同步一次——`run` 只在点击时才发请求。
  const source = handlers.source ?? 'all'
  const sync = useSyncSources(source)

  // 同步结束的提示：newCount 非空说明拿到了新增条数；state 回落 background
  // 说明轮询超时仍在后台跑，两种都要告诉用户，否则点了没反应会被当成坏了
  const prevSyncState = useRef(sync.state)
  useEffect(() => {
    const prev = prevSyncState.current
    prevSyncState.current = sync.state
    if (prev === 'syncing' && sync.state === 'idle' && sync.newCount) {
      toast.success(`同步完成，新增 ${sync.newCount} 条消息`)
    } else if (prev === 'syncing' && sync.state === 'background') {
      toast.info('同步仍在后台进行，稍后刷新查看')
    }
  }, [sync.state, sync.newCount])

  const hasLeft = slots.sources || slots.unread
  const hasRight = slots.search || slots.sync || slots.viewToggle

  return (
    <div
      className="flex flex-wrap items-center gap-1.5 border-b border-border px-4 py-2.5"
      data-testid="desk-toolbar"
      data-stage={stage}
    >
      {slots.sources && <SourcePills source={source} onSourceChange={handlers.onSourceChange} />}
      {slots.unread && <UnreadToggle {...handlers} />}
      {hasLeft && hasRight && <span className="mx-1 h-4 w-px bg-border" aria-hidden />}
      <div className="ml-auto flex items-center gap-1.5">
        {slots.search && (
          <SearchBox
            search={handlers.search ?? ''}
            onSearchChange={handlers.onSearchChange}
            searching={handlers.searching}
          />
        )}
        {/* 同步：作用域就是左边选中的档位，贴着筛选条放才能看出对应关系 */}
        {slots.sync && <SyncButton source={source} sync={sync} />}
        {slots.viewToggle && (
          <ViewToggle viewMode={handlers.viewMode ?? 'grid'} onViewModeChange={handlers.onViewModeChange} />
        )}
      </div>
    </div>
  )
}

/** 来源档位药丸：「全部 / 一张网 / 邮箱 / 法院短信 / 材料包」 */
function SourcePills({
  source,
  onSourceChange,
}: {
  source: InboxSourceFilter
  onSourceChange?: (s: InboxSourceFilter) => void
}) {
  return (
    <>
      {INBOX_SOURCE_TABS.map((tab) => (
        <button
          key={tab.key}
          type="button"
          onClick={() => onSourceChange?.(tab.key)}
          aria-pressed={source === tab.key}
          className={cn(
            'rounded-[7px] px-2.5 py-1 text-[12px] font-medium transition-colors',
            source === tab.key
              ? 'bg-foreground text-background'
              : 'text-secondary-foreground hover:bg-secondary hover:text-foreground',
          )}
        >
          {tab.label}
        </button>
      ))}
    </>
  )
}

/**
 * 未读开关 + 未读数。
 *
 * 计数按「当前筛选结果里的未读」算（由 InboxView 提供）：顶栏数字要和眼前
 * 这批消息对得上，对全库另发一个请求会得到一个解释不了的大数。
 */
function UnreadToggle({
  unreadOnly,
  onUnreadOnlyChange,
  unreadCount,
}: DeskToolbarHandlers) {
  const count = unreadCount ?? 0
  return (
    <button
      type="button"
      onClick={() => onUnreadOnlyChange?.(!unreadOnly)}
      aria-pressed={Boolean(unreadOnly)}
      className={cn(
        'flex items-center gap-1 rounded-[7px] px-2.5 py-1 text-[12px] font-medium transition-colors',
        unreadOnly
          ? 'bg-foreground text-background'
          : 'text-secondary-foreground hover:bg-secondary hover:text-foreground',
      )}
    >
      未读
      {count > 0 && (
        <span
          className={cn(
            'rounded-[99px] px-1 text-[10px] font-semibold',
            unreadOnly ? 'bg-background/20 text-background' : 'bg-status-blue-bg text-status-blue',
          )}
        >
          {count}
        </span>
      )}
    </button>
  )
}

/** 搜索框：后端 pg_trgm 索引，全库范围搜（不是只搜眼前这 200 条） */
function SearchBox({
  search,
  onSearchChange,
  searching,
}: {
  search: string
  onSearchChange?: (v: string) => void
  searching?: boolean
}) {
  return (
    <label className="flex h-[28px] w-[200px] items-center gap-1.5 rounded-[7px] border border-input bg-background px-2 transition-colors focus-within:border-ring/40">
      <Search className="h-3.5 w-3.5 flex-none text-muted-foreground" aria-hidden />
      <input
        value={search}
        onChange={(e) => onSearchChange?.(e.target.value)}
        placeholder="搜主题 / 发件人"
        aria-label="搜索收件箱"
        className="min-w-0 flex-1 bg-transparent text-[12px] outline-none placeholder:text-muted-foreground"
      />
      {searching && search && <Loader2 className="h-3 w-3 flex-none animate-spin text-muted-foreground" />}
    </label>
  )
}

const VIEW_MODES: { key: DeskViewMode; label: string; icon: ReactNode }[] = [
  { key: 'list', label: '列表', icon: <List className="h-3.5 w-3.5" aria-hidden /> },
  { key: 'grid', label: '卡片', icon: <LayoutGrid className="h-3.5 w-3.5" aria-hidden /> },
]

/**
 * 「列表 / 卡片」切换：同一批材料的两种排布，不是两套数据。
 *
 * 用分段控件而非下拉：只有两个选项，一眼能看出当前是哪种、另一种去哪点。
 */
function ViewToggle({
  viewMode,
  onViewModeChange,
}: {
  viewMode: DeskViewMode
  onViewModeChange?: (m: DeskViewMode) => void
}) {
  return (
    <div className="flex items-center gap-0.5 rounded-[7px] border border-input bg-background p-[2px]">
      {VIEW_MODES.map((m) => (
        <button
          key={m.key}
          type="button"
          onClick={() => onViewModeChange?.(m.key)}
          aria-pressed={viewMode === m.key}
          title={m.label}
          className={cn(
            'flex items-center gap-1 rounded-[6px] px-2 py-1 text-[12px] font-medium transition-colors',
            viewMode === m.key
              ? 'bg-secondary text-foreground'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {m.icon}
          {m.label}
        </button>
      ))}
    </div>
  )
}
