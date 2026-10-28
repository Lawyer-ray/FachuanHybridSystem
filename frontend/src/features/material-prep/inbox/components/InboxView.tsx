import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import { materialPrepDetail } from '@/app/paths'
import { countUnread } from '../domain'
import { useSetReadState } from '../hooks/use-inbox'
import { useInboxList } from '../hooks/use-inbox'
import { InboxList } from './InboxList'
import { MessageDrawer } from './MessageDrawer'
import type { InboxRow, InboxSourceFilter } from '../types'

/**
 * 收件箱视图 —— 预处理页「收件箱」阶段的主区域。
 *
 * 定位：**消息流入的总入口**，也就是整条漏斗的第一段（`收件箱 → 拆包 → 归案`）。
 * 它是 DeskPage 内的一个视图，不是独立页面：外壳（stage 页签、上传动作、
 * 拖放层）都由 DeskPage 提供，这里只负责列表主体与详情抽屉。
 *
 * 页面只编排：筛选/搜索/抽屉开关是本地 useState，取数走 react-query，
 * 分组与未读计数在 domain.ts（纯函数，可单测）。
 */
export function InboxView() {
  const navigate = useNavigate()
  const [source, setSource] = useState<InboxSourceFilter>('all')
  const [search, setSearch] = useState('')
  const [unreadOnly, setUnreadOnly] = useState(false)
  const [active, setActive] = useState<InboxRow | null>(null)

  const list = useInboxList({ source, unreadOnly, search })
  const setRead = useSetReadState()

  const rows = useMemo(() => list.data ?? [], [list.data])
  // 未读计数按「当前筛选结果的未读」算，不能对全库再发一个请求：
  // 顶栏那个数字要和眼前这批消息对得上
  const unreadCount = useMemo(() => countUnread(rows), [rows])

  /** 点一行：打开抽屉 + 标已读（已读的不重复请求） */
  const handleSelect = useCallback(
    (row: InboxRow) => {
      setActive(row)
      if (!row.is_read) {
        // mutate 的失败由 useSetReadState 的 onError 回滚并提示，这里不等待
        void setRead.mutate({ id: row.id, read: true })
      }
    },
    [setRead],
  )

  /** 转成材料包后：直接进材料预处理（这正是「点击后直接进入材料预处理」的闭环） */
  const goPack = useCallback(
    (packId: number) => {
      setActive(null)
      void navigate(materialPrepDetail(packId))
    },
    [navigate],
  )

  const closeDrawer = useCallback(() => {
    // 抽屉里的已读态写到列表后，active 若是旧快照会把「已读」显示回去，故清空
    setActive(null)
  }, [])

  return (
    <>
      {/* 列表容器：与材料包网格共用同一张卡片的视觉语言（圆角 + 描边 + 极轻阴影），
          让两个阶段切换时主区域"框"不跳动 */}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-[14px] border border-border bg-card shadow-[0_1px_2px_rgba(0,0,0,.02)]">
        <InboxList
          rows={rows}
          isLoading={list.isLoading}
          error={list.error}
          onRetry={() => void list.refetch()}
          source={source}
          onSourceChange={setSource}
          search={search}
          onSearchChange={setSearch}
          unreadOnly={unreadOnly}
          onUnreadOnlyChange={setUnreadOnly}
          unreadCount={unreadCount}
          activeId={active?.id ?? null}
          convertingId={null}
          onSelect={handleSelect}
        />
      </div>

      {active && <MessageDrawer row={active} onClose={closeDrawer} onConverted={goPack} />}
    </>
  )
}
