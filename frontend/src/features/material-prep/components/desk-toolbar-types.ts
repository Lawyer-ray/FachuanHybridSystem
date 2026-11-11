import type { PrepStage } from '../stages'
import type { InboxSourceFilter } from '../inbox/types'

/**
 * 预处理主页「统一工具栏」的契约（方案 B 的骨架）。
 *
 * ═══ 为什么要有这个文件 ═══
 * 收件箱阶段与材料包三态以前各有一套自己的筛选条：
 *   · 收件箱：来源档位药丸 + 未读开关 + 搜索 + 同步按钮（InboxList 内部）
 *   · 待处理：没有任何筛选条
 * 结果两个阶段的主区域是两种视觉语言，"切页签像换了页面"。
 *
 * 现在把工具栏**上提到 DeskPage**，四个阶段共用同一条；各阶段只声明自己
 * 用得到哪些控件（`view` 决定显示哪些槽位），不再各造一套。
 *
 * 这份文件只放类型与常量，不放实现——三个并行改动（外壳 / 收件箱侧 /
 * 材料包侧）都依赖它，所以它必须先生成、且保持稳定。
 */

/** 主区域呈现方式。同一批数据的两种排布，不是两套数据。 */
export type DeskViewMode = 'list' | 'grid'

/**
 * 阶段 → 默认呈现方式。
 *
 * 为什么不统一：两种排布各有不可替代的场景——
 *   · 收件箱是**消息流**，要一眼扫过几十条、按时间分组，列表才扫得动
 *   · 材料包是**待办对象**，缩略图/大卡片帮助辨认哪包是什么，网格更合适
 * 所以「默认不同、随时可切」，而不是强行统一成一种。
 */
export const STAGE_DEFAULT_VIEW: Record<PrepStage, DeskViewMode> = {
  inbox: 'list',
  todo: 'grid',
  done: 'grid',
  filed: 'grid',
}

/** 某个阶段是否提供「列表 / 卡片」切换。收件箱的数据是消息，没有卡片形态。 */
export function supportsViewToggle(stage: PrepStage): boolean {
  return stage !== 'inbox'
}

/** 统一工具栏要渲染哪些槽位（由当前阶段决定，而不是各阶段自己拼 DOM）。 */
export interface DeskToolbarSlots {
  /** 来源档位药丸（仅收件箱） */
  sources: boolean
  /** 未读开关 + 未读数（仅收件箱） */
  unread: boolean
  /** 搜索框（仅收件箱：材料包目前没有搜索接口） */
  search: boolean
  /** 「同步」按钮（仅收件箱） */
  sync: boolean
  /** 「列表 / 卡片」切换（材料包三态） */
  viewToggle: boolean
}

export function toolbarSlotsFor(stage: PrepStage): DeskToolbarSlots {
  const isInbox = stage === 'inbox'
  return {
    sources: isInbox,
    unread: isInbox,
    search: isInbox,
    sync: isInbox,
    viewToggle: supportsViewToggle(stage),
  }
}

/** 工具栏回调：只在对应槽位可见时才会被调用，各阶段可只实现关心的那几个。 */
export interface DeskToolbarHandlers {
  source?: InboxSourceFilter
  onSourceChange?: (s: InboxSourceFilter) => void
  unreadOnly?: boolean
  onUnreadOnlyChange?: (v: boolean) => void
  unreadCount?: number
  search?: string
  onSearchChange?: (v: string) => void
  searching?: boolean
  viewMode?: DeskViewMode
  onViewModeChange?: (m: DeskViewMode) => void
}

/**
 * 主区域容器样式：四个阶段**必须**共用这一个，否则又会"切页签时框跳走"。
 *
 * 以前只有收件箱外包了圆角描边卡片、材料包网格裸铺，切换时左边的框突然
 * 消失——这是"两个页面"感的主要来源之一（另一个是工具栏）。
 */
export const DESK_SURFACE_CLASS =
  'flex min-h-0 flex-1 flex-col overflow-hidden rounded-[14px] border border-border bg-card shadow-[0_1px_2px_rgba(0,0,0,.02)]'
