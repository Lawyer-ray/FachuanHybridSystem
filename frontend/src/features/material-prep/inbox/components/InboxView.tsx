import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { materialPrepDetail } from '@/app/paths'
import { countUnread } from '../domain'
import { useSetReadState } from '../hooks/use-inbox'
import { getInboxMessage } from '../api'
import { useInboxList } from '../hooks/use-inbox'
import { useSyncSources } from '../hooks/use-sync-sources'
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

  /**
   * 深链接 `?message=<id>`：自动展开那条消息的抽屉。
   *
   * 用途：首页「待认领款项」点「详情」要跳到产生这笔到账的那封原始邮件
   * （用户要看银行备注全文才知道这笔钱是谁打的）。只有落地页就把对应消息
   * 展开，这个跳转才成立——否则用户落到 300+ 条同质消息里还得自己找。
   *
   * 细节：
   * - 只在列表**加载完成**后找（加载中 rows 为空，过早查找会把"还没来"误判成"不存在"）；
   * - 参数用完即从 URL 抹掉，避免关掉抽屉后刷新又被强制弹开；
   * - 目标消息不在当前筛选结果里时（例如被 source 筛选挡掉）提示一句，
   *   而不是静默什么都不发生。
   */
  const [params, setParams] = useSearchParams()
  const deepLinkId = useMemo(() => {
    const raw = params.get('message')
    if (!raw) return null
    const id = Number(raw)
    return Number.isFinite(id) && id > 0 ? id : null
  }, [params])
  const deepLinkDone = useRef<number | null>(null)

  useEffect(() => {
    if (deepLinkId == null || list.isLoading) return
    if (deepLinkDone.current === deepLinkId) return
    deepLinkDone.current = deepLinkId
    const target = rows.find((r) => r.id === deepLinkId)
    if (target) {
      handleSelect(target)
      // 抹掉参数：抽屉打开后 URL 恢复干净，刷新不会被再次强制展开
      setParams({}, { replace: true })
      return
    }
    if (source !== 'all' || unreadOnly || search) {
      // 被当前筛选挡住了：先放开筛选再让下一轮 effect 重新找（deepLinkDone 在
      // 放开筛选前解锁，所以能重进；命中后才最终锁定，不会死循环）
      setSource('all')
      setUnreadOnly(false)
      setSearch('')
      deepLinkDone.current = null
      return
    }
    // 列表只取最近 200 条，目标消息可能更旧（到账邮件常常在几百条之外）。
    // 此时按 id 单取——详情接口的字段是列表行的超集，可直接当行用。
    let cancelled = false
    void (async () => {
      try {
        const detail = await getInboxMessage(deepLinkId)
        if (cancelled) return
        handleSelect(detail)
        setParams({}, { replace: true })
      } catch {
        if (cancelled) return
        toast.info('这条消息可能已被删除')
        setParams({}, { replace: true })
      }
    })()
    return () => {
      cancelled = true
    }
  }, [deepLinkId, list.isLoading, rows, handleSelect, setParams, source, unreadOnly, search])

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
          sync={sync}
        />
      </div>

      {active && <MessageDrawer row={active} onClose={closeDrawer} onConverted={goPack} />}
    </>
  )
}
