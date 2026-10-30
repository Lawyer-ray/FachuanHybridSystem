import { projectDetail } from '@/app/paths'
import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router'

import { ErrorBlock, LoadingBlock } from '@/components/shared/AsyncState'
import { useWorkbenchData } from '../hooks/use-workbench-data'
import type { WorkbenchDeal, WorkbenchFilter } from '../types'
import { DealRow } from './DealRow'
import { DealSheet } from './DealSheet'
import { FilterBar } from './FilterBar'

/**
 * 办案主页（路由 /projects，合同+案件融合）：合同全宽大行流 + 右侧详情抽屉。
 * 列表按后端合同接口的单一顺序（id 倒序、最新建的在前）平铺，不再按争议解决/非诉分区。
 * 交互语义（38 号原型终态 + 详情页落地）：左键行 / → = 详情页（统一 /projects/:id，
 * 诉讼/非诉由详情页按 lit 选左栏）；右键行 / 👁 = 抽屉预览。
 */

/** 默认筛选（与 FilterBar「清除全部筛选」一致）；空态判定也以它为基准 */
const DEFAULT_FILTER: WorkbenchFilter = { status: 'active', cat: '', fee: '', q: '' }

export function WorkbenchPage() {
  const navigate = useNavigate()
  const [filter, setFilter] = useState<WorkbenchFilter>(DEFAULT_FILTER)
  const [page, setPage] = useState(1)
  const { deals, total, totalPages, fetching, facets, totalContracts, activeCount, isLoading, error, refetch } =
    useWorkbenchData(filter, page)
  // open 与 deal 分离：关闭时保留 deal 引用，抽屉才能播完滑出动画（DealSheet 由 Radix 卸载）
  const [sheet, setSheet] = useState<{ open: boolean; deal: WorkbenchDeal | null }>({ open: false, deal: null })

  // 空闲预载详情页 chunk：列表行左键是最常见的下一步，点过去不等待下载。
  // 但必须等本页数据先渲染完——固定 1.5s 定时器会在首屏还在等接口时就抢带宽，
  // 800KB 级的详情 chunk 与列表请求争同一条连接。改为「数据到位后再排期」。
  const dataReady = !isLoading && !error
  useEffect(() => {
    if (!dataReady) return
    const t = window.setTimeout(() => {
      void import('./deal-detail/DealDetailPage').catch(() => {})
    }, 800)
    return () => window.clearTimeout(t)
  }, [dataReady])

  /** 左键行 / → / 抽屉「详情 →」：统一进 `/projects/:id`，页内按 lit 分流左栏 */
  const openDetail = useCallback(
    (deal: WorkbenchDeal) => {
      void navigate(projectDetail(deal.id))
    },
    [navigate],
  )
  const openSheet = useCallback((deal: WorkbenchDeal) => setSheet({ open: true, deal }), [])
  /** 筛选变化回第一页 */
  const onFilterChange = useCallback((f: WorkbenchFilter) => {
    setFilter(f)
    setPage(1)
  }, [])

  const gotoPage = useCallback((p: number) => {
    setPage(p)
    window.scrollTo({ top: 0 })
  }, [])
  // 空态判定：total 是「当前筛选命中数」、totalContracts 是全库总数（facets）。
  // 全库一条都没有（含默认视图零命中）才是真·没有项目数据；其余空列表都是筛选导致，
  // 给「清除筛选」出口。此前内外两个条件同写 deals.length === 0，「清除筛选」永不可达。
  const noFiltersActive =
    !filter.q.trim() && !filter.cat && !filter.fee && filter.status === DEFAULT_FILTER.status
  const emptyIsNoData = totalContracts === 0 || (noFiltersActive && total === 0)

  return (
    <>
      {/* 导航栏由 AppShell 常驻；入场过渡挂在 main 上，换页重挂才播一次 */}
      <main className="app-page-enter mx-auto max-w-[1460px] px-7 pt-[30px] pb-[110px]">
        {/* 页头单行：标题 + 摘要 + 搜索/筛选/chips */}
        <div className="mb-3.5 flex flex-wrap items-center gap-4">
          <h1 className="text-[21px] font-[750] tracking-[-0.02em]">办案</h1>
          {!isLoading && !error && facets && (
            <span className="text-xs whitespace-nowrap text-muted-foreground tabular-nums">
              <b className="font-semibold text-secondary-foreground">{totalContracts}</b> 个项目 ·{' '}
              <b className="font-semibold text-secondary-foreground">{activeCount}</b> 在办
            </span>
          )}
          <FilterBar facets={facets} filter={filter} onChange={onFilterChange} />
        </div>

        {isLoading ? (
          <LoadingBlock text="正在加载项目数据…" className="py-[90px]" />
        ) : error ? (
          /* hook 已把错误收成一句中文（errMessage），交给 ErrorBlock 时
             fallback 也传同一句：ErrorBlock 只对「有 message 的 Error」透出
             message，其他一律回 fallback。只换实现来源，文案必须原样 */
          <ErrorBlock
            error={error}
            fallback={error}
            onRetry={() => refetch()}
            retryText="重试"
            className="mx-auto mt-10 max-w-lg px-5 py-4 text-sm"
          />
        ) : deals.length === 0 ? (
          emptyIsNoData ? (
            <div className="py-[90px] text-center text-[13px] text-muted-foreground">还没有项目数据</div>
          ) : (
            <div className="py-[90px] text-center text-[13px] text-muted-foreground">
              没有匹配的项目
              <button
                type="button"
                className="ml-1.5 cursor-pointer underline underline-offset-3"
                onClick={() => onFilterChange(DEFAULT_FILTER)}
              >
                清除筛选
              </button>
            </div>
          )
        ) : (
          <section className="mt-2.5">
            <div className="overflow-hidden rounded-[14px] border border-border bg-card shadow-sm">
              {deals.map((d) => (
                <DealRow key={d.id} deal={d} onOpenSheet={openSheet} onOpenDetail={openDetail} />
              ))}
            </div>
          </section>
        )}
        {!isLoading && !error && total > 0 && totalPages > 1 && (
          <div className="mt-7 flex items-center justify-center gap-5 text-xs text-muted-foreground">
            <button
              type="button"
              disabled={page <= 1 || fetching}
              className="rounded-[9px] px-2.5 py-1 transition-colors hover:text-foreground disabled:pointer-events-none disabled:opacity-35"
              onClick={() => gotoPage(page - 1)}
            >
              ‹ 上一页
            </button>
            <span className="tabular-nums">
              第 {page} / {totalPages} 页 · 共 {total} 个
            </span>
            <button
              type="button"
              disabled={page >= totalPages || fetching}
              className="rounded-[9px] px-2.5 py-1 transition-colors hover:text-foreground disabled:pointer-events-none disabled:opacity-35"
              onClick={() => gotoPage(page + 1)}
            >
              下一页 ›
            </button>
          </div>
        )}
      </main>

      <DealSheet
        deal={sheet.deal}
        open={sheet.open}
        onOpenChange={(open) => !open && setSheet((s) => ({ ...s, open: false }))}
        onOpenDetail={openDetail}
      />
    </>
  )
}
