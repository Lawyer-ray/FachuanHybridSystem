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
 * 收件箱页（/inbox）。
 *
 * 定位：**消息流入的总入口**。首页右栏那张卡只展示最近 6 条，处理不了
 * 几百条历史消息；本页给完整列表 + 筛选 + 搜索 + 详情，以及「进材料预处理」
 * 的入口——这是材料预处理之前那一步真正缺的东西。
 *
 * 页面只编排：筛选/搜索/抽屉开关是本地 useState，取数走 react-query，
 * 分组与未读计数在 domain.ts（纯函数，可单测）。
 */
export function InboxPage() {
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
    <div className="relative flex min-h-[calc(100dvh-var(--app-navbar-h))] flex-col">
      <main className="app-page-enter mx-auto flex w-full max-w-[1080px] min-h-0 flex-1 flex-col px-7 pt-6 pb-8">
        <header className="mb-3 flex items-baseline gap-2.5">
          <h1 className="text-[16px] font-semibold">收件箱</h1>
          <span className="rounded-[99px] border border-border bg-secondary px-2 py-px text-[11px] font-semibold text-muted-foreground">
            {rows.length} 条
          </span>
          <span className="text-[11.5px] text-muted-foreground">
            法院送达 · 邮箱 · 短信 · 材料包，都在这里
          </span>
        </header>

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
      </main>

      {active && <MessageDrawer row={active} onClose={closeDrawer} onConverted={goPack} />}
    </div>
  )
}
