import { useEffect, useState } from 'react'
import { AlertTriangle, Gavel, RefreshCw } from 'lucide-react'

import { EmptyBlock, ErrorBlock } from '@/components/shared/AsyncState'
import { SkeletonStatus } from '@/components/shared/Skeleton'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

import type { CaseListSort } from '../api'
import { useCases } from '../hooks/use-cases'
import { CasePager } from './CasePager'
import { CaseListHeader, CaseRow } from './CaseRow'
import { CaseRowSkeleton } from './CaseRowSkeleton'

/**
 * 银行批量诉讼 · 案件列表（场景 2 的入口）。
 *
 * ═══ 这一页要回答的问题 ═══
 * 律师手上有一批银行委托，每件都处在「签约 → 立项 → 准备 → 立案 → 归档」的
 * 不同位置。这一页把**当前阶段 + 就绪度**并排放在一行，让律师一眼看出
 * 「哪几件今天就能递、哪几件卡在缺材料」。
 *
 * ═══ 为什么不直接复用现有的案件列表 ═══
 * 现有列表服务的是「全部案件」的检索浏览；这一页服务的是「批量立案」的
 * 推进节奏，列不同、排序不同（按能否立案优先），是两种任务。
 *
 * ═══ 分页 / 搜索 / 排序全部在服务端 ═══
 * 一页 50 行。前端的 filter / sort 只会作用于当前页（翻到第 2 页就会冒出与
 * 关键词无关、或「已立案」排在「待立案」前面的行），所以两个逻辑都下推成了
 * 请求参数：`search` + `sort=filable_first`（见 `api/cases.ts` 的 listCases）。
 * 页面这边不再自己筛、自己排，只负责把参数和页码交给 `useCases`。
 */

/** 每页行数（后端 limit 上限 2000，50 行是一屏多一点，翻页成本低） */
const PAGE_SIZE = 50
/** 搜索防抖：输入停 300ms 才把关键词下推，避免逐键打后端 */
const SEARCH_DEBOUNCE_MS = 300
/** 首屏骨架行数 */
const SKELETON_ROWS = 8
/** 排序口径：待立案优先（filing_number 空且在办 → 组内 id 倒序），后端算 */
const LIST_SORT: CaseListSort = 'filable_first'

/** 下发给后端的查询：关键词与页码是**一对**，必须同步变化（见下面的防抖 effect） */
interface ListQuery {
  search: string
  page: number
}

export function CaseListPage({ onOpen }: { onOpen: (caseId: number) => void }) {
  /** 输入框即时值（受控，按键立刻响应） */
  const [keyword, setKeyword] = useState('')
  const [query, setQuery] = useState<ListQuery>({ search: '', page: 1 })

  /**
   * 关键词防抖 300ms，并把「页码回 1」和关键词写进**同一次** setState。
   *
   * 为什么不用 useDebouncedValue 再配一个 `useEffect(() => setPage(1), [dq])`：
   * 防抖值落下的那一帧，useLoad 的 effect 已经带着「新关键词 + 旧页码」发了一次
   * 请求，紧接着页码回 1 又发一次——一次输入打两次后端，第二次还会把第一次的
   * 响应当成过期数据丢掉。这里把 search 与 page 合成一个 state，停顿到点才整体
   * 替换，请求参数只变一次。（值没变时返回原对象，React 直接 bail out，不出请求。）
   */
  useEffect(() => {
    const timer = window.setTimeout(() => {
      const search = keyword.trim()
      setQuery((q) => (q.search === search ? q : { search, page: 1 }))
    }, SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [keyword])

  const { loading, error, data, reload } = useCases({
    page: query.page,
    pageSize: PAGE_SIZE,
    search: query.search,
    sort: LIST_SORT,
  })

  const rows = data?.rows ?? []
  const total = data?.total ?? 0
  // 至少 1 页：0 件时「第 1 / 1 页」比「第 1 / 0 页」讲得通（分页条此时不渲染）
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

  /**
   * 页码越界回夹：数据被别人删掉（或筛选变严）后 `page > totalPages` 时，
   * 不回夹就会落到"还没有案件"的空态——明明还有数据，却被当成没有。
   * 只在请求落定后判（loading 中的 total 是旧的，回夹会打多余的一次请求）。
   */
  useEffect(() => {
    if (loading) return
    if (query.page > totalPages) setQuery((q) => ({ ...q, page: totalPages }))
  }, [loading, query.page, totalPages])

  /** 清空关键词：页码一并回 1（防抖值落地时已同值，不会再多发一次请求） */
  function clearSearch() {
    setKeyword('')
    setQuery({ search: '', page: 1 })
  }

  // 错误优先于骨架：重试失败时不该停在「正在加载」上
  if (error) return <ErrorBlock error={error} fallback="案件列表加载失败" onRetry={reload} />
  // 首次加载：data 还是 null → 与真行同源的骨架（SkeletonStatus 默认 300ms 门控，
  // 快的请求根本看不见骨架）。翻页 / 搜索时 data 里有旧值，走下面的保留列表分支。
  if (data === null) {
    return (
      <SkeletonStatus text="正在加载案件…">
        <CaseRowSkeleton count={SKELETON_ROWS} />
      </SkeletonStatus>
    )
  }
  if (!rows.length) {
    // 空态分两种：搜不到（给出口）vs 真的还没有案件（给下一步动作）
    return query.search ? (
      <EmptyBlock
        icon={<Gavel className="size-6" />}
        action={
          <Button variant="ghost" size="sm" onClick={clearSearch}>
            清除关键词
          </Button>
        }
      >
        没有匹配「{query.search}」的案件
      </EmptyBlock>
    ) : (
      <EmptyBlock icon={<Gavel className="size-6" />}>还没有案件，先受理一笔委托。</EmptyBlock>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-2">
        <input
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="搜案件名 / 案由"
          className="h-[30px] w-[240px] rounded-[7px] border border-input bg-background px-2.5 text-[12.5px] outline-none focus:border-ring/60"
        />
        <span className="text-[11.5px] text-muted-foreground">共 {total} 件</span>
        <Button variant="ghost" size="sm" className="ml-auto" onClick={reload}>
          <RefreshCw className="size-3.5" /> 刷新
        </Button>
      </div>

      {/* 翻页 / 搜索期间保留上一批行（useLoad 不清 data），只降透明度 + 标 aria-busy，
          不退回骨架：整块列表闪白一次再长回来，正是要避免的那种跳。 */}
      <div
        aria-busy={loading}
        className={cn(
          'overflow-hidden rounded-[10px] border border-border bg-card transition-opacity',
          loading && 'opacity-60',
        )}
      >
        <CaseListHeader />
        {rows.map((c, i) => (
          <CaseRow key={c.id ?? `row-${i}`} c={c} onOpen={onOpen} />
        ))}
      </div>

      <CasePager
        page={query.page}
        totalPages={totalPages}
        total={total}
        loading={loading}
        onGoto={(next) => setQuery((q) => ({ ...q, page: next }))}
      />

      <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
        <AlertTriangle className="size-3" />
        标的额取自案件登记值；实际诉请金额以利息计算表为准（两处不一致时以计算表为准）。
      </p>
    </div>
  )
}
