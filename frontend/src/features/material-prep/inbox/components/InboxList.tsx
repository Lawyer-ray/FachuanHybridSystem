import { Search, Loader2 } from 'lucide-react'

import { LoadingBlock, ErrorBlock } from '@/components/shared/AsyncState'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { INBOX_SOURCE_TABS, TIME_GROUP_LABEL, emptyHint } from '../constants'
import { groupByTime } from '../domain'
import { InboxRowItem } from './InboxRowItem'
import type { InboxRow, InboxSourceFilter } from '../types'

/**
 * 收件箱列表主体：筛选条 + 搜索 + 按时间分组的行。
 *
 * 分组用「今天/昨天/本周/更早」而非直接平铺：法院送达的紧迫性是按天衰减的，
 * 律师打开收件箱第一眼要确认的是「今天有没有新的」，分组把这个判断
 * 变成零成本（不用逐行读时间戳）。
 */
export function InboxList({
  rows,
  isLoading,
  error,
  onRetry,
  source,
  onSourceChange,
  search,
  onSearchChange,
  unreadOnly,
  onUnreadOnlyChange,
  unreadCount,
  activeId,
  convertingId,
  onSelect,
}: {
  rows: InboxRow[]
  isLoading: boolean
  error: unknown
  onRetry: () => void
  source: InboxSourceFilter
  onSourceChange: (s: InboxSourceFilter) => void
  search: string
  onSearchChange: (s: string) => void
  unreadOnly: boolean
  onUnreadOnlyChange: (v: boolean) => void
  unreadCount: number
  activeId: number | null
  convertingId: number | null
  onSelect: (row: InboxRow) => void
}) {
  const groups = groupByTime(rows)
  const isFiltering = Boolean(search.trim()) || unreadOnly || source !== 'all'

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {/* 筛选条：来源档位 + 未读开关 */}
      <div className="flex flex-wrap items-center gap-1.5 border-b border-border px-4 py-2.5">
        {INBOX_SOURCE_TABS.map((tab) => (
          <button
            key={tab.key}
            type="button"
            onClick={() => onSourceChange(tab.key)}
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
        <span className="mx-1 h-4 w-px bg-border" aria-hidden />
        <button
          type="button"
          onClick={() => onUnreadOnlyChange(!unreadOnly)}
          className={cn(
            'flex items-center gap-1 rounded-[7px] px-2.5 py-1 text-[12px] font-medium transition-colors',
            unreadOnly
              ? 'bg-foreground text-background'
              : 'text-secondary-foreground hover:bg-secondary hover:text-foreground',
          )}
        >
          未读
          {unreadCount > 0 && (
            <span
              className={cn(
                'rounded-[99px] px-1 text-[10px] font-semibold',
                unreadOnly ? 'bg-background/20 text-background' : 'bg-status-blue-bg text-status-blue',
              )}
            >
              {unreadCount}
            </span>
          )}
        </button>

        {/* 搜索：后端 pg_trgm 索引，全库范围内搜（不是只搜这 200 条） */}
        <label className="ml-auto flex h-[28px] w-[200px] items-center gap-1.5 rounded-[7px] border border-input bg-background px-2 transition-colors focus-within:border-ring/40">
          <Search className="h-3.5 w-3.5 flex-none text-muted-foreground" aria-hidden />
          <input
            value={search}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder="搜主题 / 发件人"
            className="min-w-0 flex-1 bg-transparent text-[12px] outline-none placeholder:text-muted-foreground"
          />
          {isLoading && search && <Loader2 className="h-3 w-3 flex-none animate-spin text-muted-foreground" />}
        </label>
      </div>

      {/* 列表 */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {error != null && (
          <div className="p-4">
            <ErrorBlock error={error} fallback={errMessage(error, '收件箱加载失败')} />
            <button
              type="button"
              onClick={onRetry}
              className="mx-auto mt-2 block text-[12px] underline underline-offset-3"
            >
              重试
            </button>
          </div>
        )}
        {error == null && isLoading && <LoadingBlock text="加载收件箱…" className="py-16" />}
        {error == null && !isLoading && rows.length === 0 && (
          <div className="px-4 py-16 text-center text-[12.5px] text-muted-foreground">
            {emptyHint({ unreadOnly, search, allEmpty: !isFiltering })}
          </div>
        )}
        {error == null &&
          groups.map((group) => (
            <section key={group.key}>
              <h3 className="sticky top-0 z-[1] bg-card/95 px-4 py-1.5 text-[11px] font-semibold text-muted-foreground backdrop-blur-[2px]">
                {TIME_GROUP_LABEL[group.key]}
                <span className="ml-1.5 font-normal">({group.rows.length})</span>
              </h3>
              <div className="divide-y divide-border/70">
                {group.rows.map((row) => (
                  <InboxRowItem
                    key={row.id}
                    row={row}
                    active={activeId === row.id}
                    converting={convertingId === row.id}
                    onSelect={onSelect}
                  />
                ))}
              </div>
            </section>
          ))}
      </div>
    </div>
  )
}
