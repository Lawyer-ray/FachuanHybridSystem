import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { materialPrepDetail } from '@/app/paths'
import { useSetReadState } from '../hooks/use-inbox'
import { getInboxMessage } from '../api'
import { useInboxList } from '../hooks/use-inbox'
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

  /** 转成材料包后：直接进材料预处理（这正是「点击后直接进入材料预处理」的闭环） */
  const goPack = useCallback(
    (packId: number) => {
      setActive(null)
      void navigate(materialPrepDetail(packId))
    },
    [navigate, setActive],
  )

  const closeDrawer = useCallback(() => {
    // 抽屉里的已读态写到列表后，active 若是旧快照会把「已读」显示回去，故清空
    setActive(null)
  }, [setActive])

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
   * - 目标消息不在当前筛选结果里时（例如被 source 筛选挡掉）先放开筛选，
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
      // 被当前筛选挡住了：放开筛选（改的是父级状态，工具栏与之一致），
      // 再让下一轮 effect 重新找（deepLinkDone 在放开筛选前解锁，所以能重进；
      // 命中后才最终锁定，不会死循环）
      if (source !== 'all') onSourceChange('all')
      if (unreadOnly) onUnreadOnlyChange(false)
      if (search) onSearchChange('')
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
  }, [
    deepLinkId,
    list.isLoading,
    rows,
    handleSelect,
    setParams,
    source,
    unreadOnly,
    search,
    onSourceChange,
    onUnreadOnlyChange,
    onSearchChange,
  ])

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
          convertingId={null}
          onSelect={handleSelect}
        />
      </div>

      {active && <MessageDrawer row={active} onClose={closeDrawer} onConverted={goPack} />}
    </>
  )
}
