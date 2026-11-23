import { useEffect, useMemo, useRef } from 'react'
import { useSearchParams } from 'react-router'
import { toast } from 'sonner'

import { getInboxMessage } from '../api'
import type { InboxRow, InboxSourceFilter } from '../types'

/**
 * 深链接 `?message=<id>`：列表落地后自动展开那条消息的抽屉。
 *
 * 用途：首页「待认领款项」点「详情」要跳到产生这笔到账的那封原始邮件
 * （用户要看银行备注全文才知道这笔钱是谁打的）。只有落地页就把对应消息
 * 展开，这个跳转才成立——否则用户落到 300+ 条同质消息里还得自己找。
 *
 * 参数解析与抹除都留在本 hook 里：`?message=` 是这条链路唯一的入口与出口，
 * 散到视图里会让「谁负责用掉它」变得不可核对。
 *
 * 细节：
 * - 只在列表**加载完成**后找（加载中 rows 为空，过早查找会把"还没来"误判成"不存在"）；
 * - 参数用完即从 URL 抹掉，避免关掉抽屉后刷新又被强制弹开；
 * - 目标消息不在当前筛选结果里时（例如被 source 筛选挡掉）先放开筛选，
 *   而不是静默什么都不发生。
 */
export interface DeepLinkMessageOptions {
  /** 当前列表行（首页取回的最近 200 条） */
  rows: InboxRow[]
  isLoading: boolean
  /** 打开抽屉（含标已读） */
  select: (row: InboxRow) => void
  /** 当前筛选档位与筛选值，受控于 DeskPage 的统一工具栏 */
  source: InboxSourceFilter
  unreadOnly: boolean
  search: string
  /** 放开筛选：改的是父级状态（工具栏与列表共用同一份真值） */
  onSourceChange: (s: InboxSourceFilter) => void
  onUnreadOnlyChange: (v: boolean) => void
  onSearchChange: (v: string) => void
}

export function useDeepLinkMessage({
  rows,
  isLoading,
  select,
  source,
  unreadOnly,
  search,
  onSourceChange,
  onUnreadOnlyChange,
  onSearchChange,
}: DeepLinkMessageOptions): void {
  const [params, setParams] = useSearchParams()
  const deepLinkId = useMemo(() => {
    const raw = params.get('message')
    if (!raw) return null
    const id = Number(raw)
    return Number.isFinite(id) && id > 0 ? id : null
  }, [params])
  /** 已处理过的目标 id：同一条只展开一次 */
  const doneRef = useRef<number | null>(null)

  useEffect(() => {
    if (deepLinkId == null || isLoading) return
    if (doneRef.current === deepLinkId) return
    doneRef.current = deepLinkId
    const target = rows.find((r) => r.id === deepLinkId)
    if (target) {
      select(target)
      // 抹掉参数：抽屉打开后 URL 恢复干净，刷新不会被再次强制展开
      setParams({}, { replace: true })
      return
    }
    if (source !== 'all' || unreadOnly || search) {
      // 被当前筛选挡住了：放开筛选（改的是父级状态，工具栏与之一致），
      // 再让下一轮 effect 重新找（doneRef 在放开筛选前解锁，所以能重进；
      // 命中后才最终锁定，不会死循环）
      if (source !== 'all') onSourceChange('all')
      if (unreadOnly) onUnreadOnlyChange(false)
      if (search) onSearchChange('')
      doneRef.current = null
      return
    }
    // 列表只取最近 200 条，目标消息可能更旧（到账邮件常常在几百条之外）。
    // 此时按 id 单取——详情接口的字段是列表行的超集，可直接当行用。
    let cancelled = false
    void (async () => {
      try {
        const detail = await getInboxMessage(deepLinkId)
        if (cancelled) return
        select(detail)
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
    isLoading,
    rows,
    select,
    setParams,
    source,
    unreadOnly,
    search,
    onSourceChange,
    onUnreadOnlyChange,
    onSearchChange,
  ])
}
