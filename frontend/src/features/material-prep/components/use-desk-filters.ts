import { useCallback, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router'
import { isPackStage, parseStage, stageToQuery, type PrepStage } from '../stages'
import { useInboxList } from '../inbox/hooks/use-inbox'
import { countUnread } from '../inbox/domain'
import type { InboxSourceFilter } from '../inbox/types'
import type { PackStatus } from '../types'
import { STAGE_DEFAULT_VIEW } from './desk-toolbar-types'
import type { DeskViewMode } from './desk-toolbar-types'

type Tab = PackStatus

/**
 * DeskPage 的「导航 + 筛选」状态簇：阶段、材料包三态页签、卡片选中索引、
 * 统一工具栏的筛选值（来源档位 / 搜索 / 只看未读）、按阶段记住的列表-卡片形态。
 *
 * 为什么成簇住在这里：这些 state 都是「页面在看哪一批东西」的表达，工具栏、
 * 收件箱主体、材料包网格三处消费的是同一份真值。它们此前散落在页面组件里，
 * 与上传 / 离场动画 / 弹窗等编排逻辑混在一起，读代码时看不出哪几个是一组。
 */
export function useDeskFilters() {
  // 阶段入 URL（?stage=todo）：可刷新、可分享、可前进后退。收件箱里的
  // 「转材料包」闭环也靠它跳到待处理，而不是另写一套页内状态。
  const [params, setParams] = useSearchParams()
  const stage = parseStage(params.get('stage'))
  // 材料包三态页签的当前值（收件箱阶段下沿用上一次的三态，供 PackGrid/键盘导航用）
  const [packTab, setPackTab] = useState<Tab>('todo')
  const tab: Tab = isPackStage(stage) ? stage : packTab

  const [sel, setSel] = useState(0)

  // ── 统一工具栏的筛选状态 ──────────────────────────────────
  // 收件箱的筛选以前是 InboxView 内部的本地 state，工具栏上提到页面级后
  // 必须跟着上提：工具栏与列表主体是兄弟节点，状态留在下面就会出现
  // 「点了药丸但列表不动」。InboxView 现在是受控组件，只认这里的值。
  const [source, setSource] = useState<InboxSourceFilter>('all')
  const [search, setSearch] = useState('')
  const [unreadOnly, setUnreadOnly] = useState(false)

  // 「未读」药丸上的数字：**当前来源档位 + 搜索词下的未读条数**，与未读开关无关。
  //
  // 关键：这里**不传 `unreadOnly`**。它是发给后端的查询参数（unread_only=true），
  // 传了就会只拿回未读行，数字被自己的开关坍缩——开关一翻，数字跟着抖甚至自指。
  // 语义上两者本就不同：「要不要只看未读」是筛选意图，「这里有多少未读」是事实。
  //
  // 另：不能对全库另发请求——顶栏那个数要和眼前这批消息对得上。
  const inboxRows = useInboxList({ source, search })
  const unreadCount = useMemo(
    () => countUnread(inboxRows.data ?? []),
    [inboxRows.data],
  )

  // 「列表 / 卡片」按阶段分别记住用户的切换结果：从「待处理」切到「已归案」
  // 再切回来，待处理仍然是他上次选的那种排布。只在内存里，不持久化——
  // 刷新后回到 STAGE_DEFAULT_VIEW 的缺省（消息流用列表、材料包用卡片）。
  const [viewModes, setViewModes] = useState<
    Partial<Record<PrepStage, DeskViewMode>>
  >({})
  const viewMode: DeskViewMode = viewModes[stage] ?? STAGE_DEFAULT_VIEW[stage]
  const setViewMode = useCallback(
    (m: DeskViewMode) => setViewModes((prev) => ({ ...prev, [stage]: m })),
    [stage],
  )

  const setStage = useCallback(
    (s: PrepStage) => {
      if (isPackStage(s)) setPackTab(s)
      setSel(0)
      // 只在**现有参数上**改 stage，不整体替换。
      // setParams 传对象是覆盖语义：以前直接 setParams({stage:s}) 会把
      // 深链接的 ?message=<id> 一起抹掉（收件箱打开某条消息的直达能力失效）。
      setParams(
        (prev) => {
          const next = new URLSearchParams(prev)
          // 收件箱是默认阶段：不往 URL 里写冗余参数，保持 /material-prep 干净
          const q = stageToQuery(s)
          if (q == null) next.delete('stage')
          else next.set('stage', q)
          return next
        },
        { replace: true },
      )
    },
    [setParams, setPackTab, setSel],
  )

  return {
    stage,
    tab,
    setStage,
    sel,
    setSel,
    source,
    setSource,
    search,
    setSearch,
    unreadOnly,
    setUnreadOnly,
    unreadCount,
    viewMode,
    setViewMode,
  }
}
