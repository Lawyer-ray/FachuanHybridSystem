import { LoadingBlock, ErrorBlock } from '@/components/shared/AsyncState'
import { errMessage } from '@/lib/errors'
import { INBOX_EMPTY_GUIDE, TIME_GROUP_LABEL, emptyHint } from '../constants'
import { groupByTime } from '../domain'
import { InboxRowItem } from './InboxRowItem'
import type { InboxRow, InboxSourceFilter } from '../types'

/**
 * 收件箱列表主体：按时间分组的行。
 *
 * 筛选控件（来源档位 / 未读 / 搜索 / 同步）**不在这里**：它们已上提到
 * DeskPage 的统一工具栏（见 material-prep/components/desk-toolbar-types.ts），
 * 四个阶段共用同一条工具栏，收件箱不再自造一条二级筛选条。
 * 本组件只接收受控的筛选值（用于分组、空态判定与重试展示），不持有状态。
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
  search,
  unreadOnly,
  activeId,
  convertingId,
  onSelect,
}: {
  rows: InboxRow[]
  isLoading: boolean
  error: unknown
  onRetry: () => void
  /** 当前档位：只用于空态选哪条通路说明，筛选动作由工具栏承担 */
  source: InboxSourceFilter
  search: string
  unreadOnly: boolean
  activeId: number | null
  convertingId: number | null
  onSelect: (row: InboxRow) => void
}) {
  const groups = groupByTime(rows)
  // 空态指引关心的是「用户是否在主动缩小结果」（搜索 / 只看未读），
  // 而不是「选了某个档位」——档位就是用户在选通路本身。
  // 用「档位也算筛选」会把「刚切到法院短信档」误判成「筛选后为空」，
  // 从而把通路说明降级成通用的「暂无消息」。
  const narrowed = Boolean(search.trim()) || unreadOnly

  return (
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
  )
}

/**
 * 空态。
 *
 * 两种情况必须分开表达：
 * - **通路未接入**（INBOX_EMPTY_GUIDE 有该档位的说明）：等多久都不会有数据，
 *   直接告诉用户去哪看，并给可点的入口。不写「暂无消息」——那会让人反复刷新。
 * - **筛选后为空**：搜索/未读把结果筛没了，只提示「换个条件」。
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
