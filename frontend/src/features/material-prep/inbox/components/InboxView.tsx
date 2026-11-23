import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import { materialPrepDetail } from '@/app/paths'
import { useInboxList, useSetReadState } from '../hooks/use-inbox'
import { useDeepLinkMessage } from '../hooks/use-deep-link-message'
import { InboxList } from './InboxList'
import { MessageDrawer } from './MessageDrawer'
import type { InboxRow, InboxSourceFilter } from '../types'

/** 收件箱筛选状态：受控于 DeskPage，与统一工具栏共用同一份真值。 */
export interface InboxViewProps {
  source: InboxSourceFilter
  onSourceChange: (s: InboxSourceFilter) => void
  search: string
  onSearchChange: (v: string) => void
  unreadOnly: boolean
  onUnreadOnlyChange: (v: boolean) => void
}

/**
 * 收件箱视图 —— 预处理页「收件箱」阶段的主区域。
 *
 * 定位：**消息流入的总入口**，也就是整条漏斗的第一段（`收件箱 → 拆包 → 归案`）。
 * 它是 DeskPage 内的一个视图，不是独立页面：外壳（阶段页签、统一工具栏、上传动作、
 * 拖放层、主区域卡片容器）都由 DeskPage 提供，这里只负责列表主体与详情抽屉。
 *
 * 筛选状态（来源档位 / 搜索 / 只看未读）**由父级 DeskPage 受控**：这些控件已上提到
 * 统一工具栏，四个阶段共用一条；本视图不再持有它们，只负责取数、分组与详情抽屉。
 *
 * 同步（含它的状态机与「同步完成/仍在后台」提示）也归工具栏自持：按钮在
 * DeskToolbar 里，状态机必须与按钮同域，否则工具栏点了同步、本视图这份仍是
 * idle，提示永远不会触发。
 */
export function InboxView({
  source,
  onSourceChange,
  search,
  onSearchChange,
  unreadOnly,
  onUnreadOnlyChange,
}: InboxViewProps) {
  // 未读条数不从这里出：本视图的 rows 是按 unreadOnly 取回来的，
  // 打开「只看未读」后 rows 里没有未读行，在这里算必然恒为 0。
  // 它由 DeskPage 用「不带 unreadOnly」的口径计算并只用于工具栏显示。
  const navigate = useNavigate()
  const [active, setActive] = useState<InboxRow | null>(null)

  const list = useInboxList({ source, unreadOnly, search })
  const setRead = useSetReadState()

  const rows = useMemo(() => list.data ?? [], [list.data])

  /** 点一行：打开抽屉 + 标已读（已读的不重复请求） */
  const handleSelect = useCallback(
    (row: InboxRow) => {
      setActive(row)
      if (!row.is_read) {
        // mutate 的失败由 useSetReadState 的 onError 回滚并提示，这里不等待
        void setRead.mutate({ id: row.id, read: true })
      }
    },
    [setActive, setRead],
  )

  // 深链接 `?message=<id>`：自动展开对应消息的抽屉（首页「待认领款项」的落点）。
  // 解析/抹除参数、放开挡路筛选、按 id 单取旧消息都在 hook 里，本视图只给现状。
  useDeepLinkMessage({
    rows,
    isLoading: list.isLoading,
    select: handleSelect,
    source,
    unreadOnly,
    search,
    onSourceChange,
    onUnreadOnlyChange,
    onSearchChange,
  })

  /** 转成材料包后：直接进材料预处理（这正是「点击后直接进入材料预处理」的闭环）。
   *
   * 带上 ?stage=todo：转到的是**材料包**、且刚建出来必然是「待处理」。
   * 不带 stage 的话详情路由会回落成「收件箱」，打开时先闪一帧收件箱列表。
   */
  const goPack = useCallback(
    (packId: number) => {
      setActive(null)
      void navigate(`${materialPrepDetail(packId)}?stage=todo`)
    },
    [navigate, setActive],
  )

  const closeDrawer = useCallback(() => {
    // 抽屉里的已读态写到列表后，active 若是旧快照会把「已读」显示回去，故清空
    setActive(null)
  }, [setActive])

  return (
    <>
      {/* 主区域的圆角描边卡片由 DeskPage 的 DESK_SURFACE_CLASS 提供（四阶段共用
          同一个框，切页签时框不跳），因此这里只做普通 flex 列容器、不再自带
          边框，否则会叠出双层描边。 */}
      <div className="flex min-h-0 flex-1 flex-col">
        <InboxList
          rows={rows}
          isLoading={list.isLoading}
          error={list.error}
          onRetry={() => void list.refetch()}
          source={source}
          search={search}
          unreadOnly={unreadOnly}
          activeId={active?.id ?? null}
          onSelect={handleSelect}
        />
      </div>

      {active && <MessageDrawer row={active} onClose={closeDrawer} onConverted={goPack} />}
    </>
  )
}
