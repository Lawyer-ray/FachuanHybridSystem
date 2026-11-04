import { Search, Loader2 } from 'lucide-react'

import { LoadingBlock, ErrorBlock } from '@/components/shared/AsyncState'
import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { INBOX_EMPTY_GUIDE, INBOX_SOURCE_TABS, TIME_GROUP_LABEL, emptyHint } from '../constants'
import { groupByTime } from '../domain'
import { InboxRowItem } from './InboxRowItem'
import { SyncButton } from './SyncButton'
import type { SyncResult } from '../hooks/use-sync-sources'
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
  sync,
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
  /** 同步按钮状态机（由 InboxView 按当前 source 档位创建） */
  sync: SyncResult
}) {
  const groups = groupByTime(rows)
  // 空态指引关心的是「用户是否在主动缩小结果」（搜索 / 只看未读），
  // 而不是「选了某个档位」——档位就是用户在选通路本身。
  // 用「档位也算筛选」会把「刚切到法院短信档」误判成「筛选后为空」，
  // 从而把通路说明降级成通用的「暂无消息」。
  const narrowed = Boolean(search.trim()) || unreadOnly

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

        {/* 同步：作用于当前选中的来源档位。放在筛选条最右端，让「同步范围」与
            「当前筛选」在视觉上绑定 —— 放顶栏会与筛选状态脱节产生歧义 */}
        <SyncButton source={source} sync={sync} />
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
          <InboxEmpty source={source} narrowed={narrowed} unreadOnly={unreadOnly} search={search} />
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

/**
 * 空态。
 *
 * 两种情况必须分开表达：
 * - **通路未接入**（INBOX_EMPTY_GUIDE 有该档位的说明）：等多久都不会有数据，
 *   直接告诉用户去哪看，并给可点的入口。不写「暂无消息」——那会让人反复刷新。
 * - **筛选后为空**：搜索/未读/档位过滤把结果筛没了，只提示「换个条件」。
 *
 * 只在**未筛选**时才展示通路说明：用户正在搜索时给一大块说明会打断他。
 */
function InboxEmpty({
  source,
  narrowed,
  unreadOnly,
  search,
}: {
  source: InboxSourceFilter
  /** 搜索/未读把结果筛没了（不含「选了哪个档位」） */
  narrowed: boolean
  unreadOnly: boolean
  search: string
}) {
  const guide = narrowed ? undefined : INBOX_EMPTY_GUIDE[source]

  if (guide) {
    return (
      <div className="px-4 py-16 text-center">
        <p className="text-[13px] font-medium text-foreground">{guide.title}</p>
        <p className="mx-auto mt-1.5 max-w-[320px] text-[12px] leading-relaxed text-muted-foreground">
          {guide.description}
        </p>
        {guide.href && (
          <a
            href={guide.href}
            target="_blank"
            rel="noreferrer"
            className="mt-4 inline-block rounded-[7px] border border-input bg-background px-3 py-1.5 text-[12px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
          >
            {guide.linkText ?? '前往查看'} →
          </a>
        )}
      </div>
    )
  }

  return (
    <div className="px-4 py-16 text-center text-[12.5px] text-muted-foreground">
      {/* allEmpty：只有「全部档位 + 没有任何筛选」才是真的收件箱全空；
          其余情况都只是「这一分类下」为空，文案要区分开 */}
      {emptyHint({ unreadOnly, search, allEmpty: !narrowed && source === 'all' })}
    </div>
  )
}
