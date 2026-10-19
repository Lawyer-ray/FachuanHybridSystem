import { Check } from 'lucide-react'

import type { CalendarEvent } from '../api'
import { formatCN, parseKey } from '../domain'
import { briefLine, cellMetaLines } from '../api-meta'
import { KIND_ROW } from '../constants'
import { isKeyKind } from '../api-meta'
import { cn } from '@/lib/utils'

/**
 * 月历的单日格（从 CalendarPanel.tsx 拆出）：事件行（桌面）/ 标题截断（手机）、
 * 完成勾选、悬停摘要。纯展示受控组件，选中态与数据都在 CalendarPanel。
 */

/** 格子高度：桌面按视口自适应；手机端只放日期行 + 两条标题，压到 72px 让整月基本一屏可见
 *  （原先手机沿用桌面的 132px 起步，一屏只见两三周，还全是空白） */
const CELL_HEIGHT = 'min-h-[clamp(132px,12vw,208px)] max-[760px]:min-h-[72px]'

/** 手机端格子里最多显示几条标题（再多折叠成 +N，全文进当日抽屉） */
const MOBILE_TITLE_ROWS = 2

interface CellProps {
  cell: { key: string | null; day: number | null; inMonth: boolean }
  today: string
  selected: boolean
  events: CalendarEvent[]
  maxRows: number
  /** 手机断点：点格子任意位置都开当日抽屉，不区分空白 / 事件 */
  mobile: boolean
  onPick: (key: string) => void
  onOpenDetail: (e: CalendarEvent) => void
  /** 点日历格空白处 → 新增该日安排（仅桌面端） */
  onOpenAdd: (key: string) => void
  /** 勾选完成 / 取消完成 */
  onToggleComplete: (e: CalendarEvent) => void
}

export function DayCell({ cell, today, selected, events, maxRows, mobile, onPick, onOpenAdd, onOpenDetail, onToggleComplete }: CellProps) {
  if (!cell.key || cell.day == null) return <div className={cn(CELL_HEIGHT, 'border-r border-b border-border-light')} />

  const key = cell.key
  const isToday = key === today
  const shown = events.slice(0, maxRows)
  const hidden = events.length - shown.length
  const mobileHidden = events.length - Math.min(events.length, MOBILE_TITLE_ROWS)

  return (
    <div
      role="button"
      tabIndex={0}
      aria-label={`${cell.day} 日${events.length ? `，${events.length} 个安排` : ''}，${mobile ? '点按查看该日安排' : '回车新增该日安排'}`}
      className={cn(
        'group relative cursor-pointer border-r border-b border-border-light p-[7px] transition-colors last:border-r-0 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-inset max-[760px]:p-[4px]',
        CELL_HEIGHT,
        !cell.inMonth && 'opacity-30',
        selected && 'bg-secondary/60',
        isToday && 'bg-status-red-bg/40',
      )}
      onClick={(ev) => {
        // 手机端：格子里没有可点准的事件行，点哪儿都是「看这一天」→ 开当日抽屉，
        // 新增走抽屉里的「＋新增」。以前这里也走「点空白新增」：手机上事件只是
        // 不可交互的圆点，点圆点穿透成新增弹窗，详情永远开不了
        if (mobile) {
          onPick(key)
          return
        }
        // 点在事件行 / 「+N 更多」上不算"点空白处"，只选中该日（新增弹窗由 onOpenAdd 负责）
        const target = ev.target as HTMLElement
        if (target.closest('[data-calendar-event], [data-calendar-more]')) {
          onPick(key)
          return
        }
        onOpenAdd(key)
      }}
      onKeyDown={(ev) => {
        // 键盘可达：Enter / Space 等价于点格子（桌面=打开该日新增；手机=开抽屉）；事件行详情见事件行自身的 onKeyDown
        if (ev.key === 'Enter' || ev.key === ' ') {
          ev.preventDefault()
          onPick(key)
          if (!mobile) onOpenAdd(key)
        }
      }}
      title={mobile ? undefined : '点空白处新增该日安排'}
    >
      <div className="mb-[5px] flex items-center justify-center gap-[3px]">
        <span
          className={cn(
            'flex h-[22px] w-[22px] items-center justify-center rounded-full text-[12px] leading-none font-medium tabular-nums',
            isToday && 'bg-status-red font-bold text-white',
          )}
        >
          {cell.day}
        </span>
        {/* 当日条数角标：与 admin 日历的 reminder-day-count 一致 */}
        {events.length > 0 && (
          <span className="rounded-full border border-border bg-secondary px-[5px] py-[1px] text-[9px] font-semibold tabular-nums text-muted-foreground">
            {events.length}
          </span>
        )}
      </div>

      <div className={cn('flex flex-col gap-[2px]', 'max-[760px]:hidden')}>
        {shown.map((e) => {
          const meta = cellMetaLines(e)
          return (
            <div
              key={e.id}
              data-calendar-event={e.id}
              role="button"
              tabIndex={0}
              className={cn(
                'flex flex-col justify-center gap-px rounded-[5px] px-[6px] py-[3px] text-[11.5px] transition-[filter] hover:brightness-95',
                KIND_ROW[e.kind],
                !isKeyKind(e.kind) && 'bg-secondary/70',
                e.is_completed && 'opacity-55',
              )}
              onClick={(ev) => {
                ev.stopPropagation()
                onOpenDetail(e)
              }}
              onKeyDown={(ev) => {
                // 键盘可达：Enter / Space 打开事件详情（等价点击事件行）
                if (ev.key !== 'Enter' && ev.key !== ' ') return
                // 行首完成勾选按钮自身可激活，按键交给按钮，不重复触发详情
                if ((ev.target as HTMLElement).closest('button')) return
                ev.preventDefault()
                // 不冒泡到日历格（否则会触发「点空白处新增」）
                ev.stopPropagation()
                onOpenDetail(e)
              }}
            >
              {/* 时间独占第一行，正文全部左对齐顶格开始。
                  以前把时间做成固定 30px 的前导列，导致律师/地点两行要缩进
                  到 30px 起，左侧白费一条——格子本来就窄，不能再浪费宽度。
                  行首的完成勾选与时间同行，已完成时标题划线。 */}
              <span className="flex items-center gap-1">
                <button
                  type="button"
                  aria-label={e.is_completed ? '标记为未完成' : '标记为完成'}
                  title={e.is_completed ? '标记为未完成' : '标记为完成'}
                  onClick={(ev) => {
                    // 勾选只切换完成态：不冒泡到事件行（详情）与日历格（新增）
                    ev.stopPropagation()
                    onToggleComplete(e)
                  }}
                  className={cn(
                    'flex h-[12px] w-[12px] flex-none items-center justify-center rounded-full border-[1.5px] transition-colors',
                    e.is_completed
                      ? 'border-foreground bg-foreground text-background'
                      : 'border-current/40 text-transparent hover:border-current',
                  )}
                >
                  <Check className="h-[8px] w-[8px]" strokeWidth={3} />
                </button>
                <span className="text-[10px] font-semibold tabular-nums opacity-80">{e.time}</span>
                {e.time_range && e.time_range !== e.time && (
                  <span className="truncate text-[9px] tabular-nums opacity-55">-{e.time_range.split('-')[1]}</span>
                )}
              </span>
              <span className={cn('truncate font-medium leading-tight', e.is_completed && 'line-through')}>{e.title}</span>
              {meta.primary && <span className="truncate text-[9.5px] opacity-75">{meta.primary}</span>}
              {meta.secondary && <span className="truncate text-[9.5px] opacity-60">{meta.secondary}</span>}
            </div>
          )
        })}
        {hidden > 0 && (
          <span
            data-calendar-more
            className="mt-[1px] self-start rounded-[6px] border border-input bg-secondary px-2 py-[2px] text-[10.5px] font-semibold text-secondary-foreground"
          >
            + {hidden} 更多
          </span>
        )}
      </div>

      {/* 手机端：圆点 + 标题截断。格子仅 ~50px 宽，只够看开头几个字和紧要色，
          全文进当日抽屉（点格子即开）；纯展示不拦点击，整格一个点击目标 */}
      {events.length > 0 && (
        <div aria-hidden data-calendar-mobile-titles className="mt-[2px] hidden flex-col gap-[2px] max-[760px]:flex">
          {events.slice(0, MOBILE_TITLE_ROWS).map((e) => (
            <span key={e.id} className={cn('flex min-w-0 items-center gap-[3px]', e.is_completed && 'opacity-40')}>
              <i className={cn('h-[5px] w-[5px] flex-none rounded-full', isKeyKind(e.kind) ? 'bg-status-red' : 'bg-input')} />
              <span className={cn('truncate text-[9.5px] leading-[1.3]', e.is_completed && 'line-through')}>{e.title}</span>
            </span>
          ))}
          {mobileHidden > 0 && <em className="text-[9px] leading-none text-muted-foreground">+{mobileHidden}</em>}
        </div>
      )}

      {/* 悬停摘要 */}
      {events.length > 0 && (
        <div className="pointer-events-none absolute bottom-[calc(100%+4px)] left-1/2 z-40 hidden w-[300px] max-w-[330px] -translate-x-1/2 scale-95 rounded-[11px] bg-foreground p-[11px_14px] text-[11.5px] leading-[1.5] text-background opacity-0 shadow-[0_8px_24px_rgba(0,0,0,.16)] transition-[opacity,transform,visibility] group-hover:visible group-hover:scale-100 group-hover:opacity-100 min-[761px]:block">
          <div className="mb-1.5 text-[10px] text-background/60">
            {/* parseKey 而非 new Date(key)：后者按 UTC 零点解析，西半球时区会退一天 */}
            {(isToday ? '今天 · ' : '') + formatCN(parseKey(key))}
          </div>
          {events.map((e) => (
            <div key={e.id} className={cn('flex items-baseline gap-[7px]', e.is_completed && 'opacity-60')}>
              <span className="w-8 flex-none text-[10px] text-background/60 tabular-nums">{e.time}</span>
              <span className={cn('truncate font-medium', e.is_completed && 'line-through')}>{e.title}</span>
              <span className="max-w-[110px] truncate text-[10.5px] text-background/50">{briefLine(e)}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
