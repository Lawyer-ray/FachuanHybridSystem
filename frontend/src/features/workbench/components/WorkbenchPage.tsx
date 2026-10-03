import { useCallback, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { AppNavbar } from '@/components/shared/AppNavbar'
import { PageFade } from '@/components/shared/PageFade'
import { groupDeals } from '../domain'
import { useWorkbenchData } from '../hooks/use-workbench-data'
import type { WorkbenchDeal, WorkbenchFilter } from '../types'
import { DealRow } from './DealRow'
import { DealSheet } from './DealSheet'
import { FilterBar } from './FilterBar'

/**
 * 办案主页：合同全宽大行流 + 类型分组 + 右侧详情抽屉。
 * 交互语义（与 38 号原型终态一致）：
 * 左键行 / → = 详情页（开发中提示）；右键行 / 👁 = 抽屉预览。
 */

/** 默认筛选（与 FilterBar「清除全部筛选」一致）；空态判定也以它为基准 */
const DEFAULT_FILTER: WorkbenchFilter = { status: 'active', cat: '', fee: '', q: '' }

export function WorkbenchPage() {
  const [filter, setFilter] = useState<WorkbenchFilter>(DEFAULT_FILTER)
  const [page, setPage] = useState(1)
  const { deals, total, totalPages, fetching, facets, totalContracts, activeCount, isLoading, error, refetch } =
    useWorkbenchData(filter, page)
  // open 与 deal 分离：关闭时保留 deal 引用，抽屉才能播完滑出动画（DealSheet 由 Radix 卸载）
  const [sheet, setSheet] = useState<{ open: boolean; deal: WorkbenchDeal | null }>({ open: false, deal: null })

  const notify = useCallback((msg: string) => toast.info(msg), [])
  const detailNotReady = useCallback(() => toast.info('详情页正在开发中（右键行 = 快速预览）'), [])
  const openSheet = useCallback((deal: WorkbenchDeal) => setSheet({ open: true, deal }), [])
  /** 筛选变化回第一页 */
  const onFilterChange = useCallback((f: WorkbenchFilter) => {
    setFilter(f)
    setPage(1)
  }, [])

  const groups = useMemo(() => groupDeals(deals, !!filter.cat), [deals, filter.cat])
  const gotoPage = useCallback((p: number) => {
    setPage(p)
    window.scrollTo({ top: 0 })
  }, [])
  // 空态判定：total 是「当前筛选命中数」、totalContracts 是全库总数（facets）。
  // 全库一条都没有（含默认视图零命中）才是真·没有合同数据；其余空列表都是筛选导致，
  // 给「清除筛选」出口。此前内外两个条件同写 deals.length === 0，「清除筛选」永不可达。
  const noFiltersActive =
    !filter.q.trim() && !filter.cat && !filter.fee && filter.status === DEFAULT_FILTER.status
  const emptyIsNoData = totalContracts === 0 || (noFiltersActive && total === 0)

  return (
    <div className="min-h-screen bg-background">
      <AppNavbar onNotify={notify} />
      <PageFade>
        <main className="mx-auto max-w-[1460px] px-7 pt-[30px] pb-[110px]">
          {/* 页头单行：标题 + 摘要 + 搜索/筛选/chips */}
          <div className="mb-3.5 flex flex-wrap items-center gap-4">
            <h1 className="text-[21px] font-[750] tracking-[-0.02em]">办案</h1>
            {!isLoading && !error && facets && (
              <span className="text-xs whitespace-nowrap text-muted-foreground tabular-nums">
                <b className="font-semibold text-secondary-foreground">{totalContracts}</b> 个合同 ·{' '}
                <b className="font-semibold text-secondary-foreground">{activeCount}</b> 在办
              </span>
            )}
            <FilterBar facets={facets} filter={filter} onChange={onFilterChange} />
          </div>

          {isLoading ? (
            <div className="flex flex-col items-center gap-2 py-[90px] text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" />
              正在加载办案数据…
            </div>
          ) : error ? (
            <div className="mx-auto mt-10 max-w-lg rounded-[14px] border border-destructive/30 bg-destructive/5 px-5 py-4 text-center text-sm text-destructive">
              {error}
              <button type="button" className="ml-3 underline underline-offset-3" onClick={() => refetch()}>
                重试
              </button>
            </div>
          ) : deals.length === 0 ? (
            emptyIsNoData ? (
              <div className="py-[90px] text-center text-[13px] text-muted-foreground">还没有合同数据</div>
            ) : (
              <div className="py-[90px] text-center text-[13px] text-muted-foreground">
                没有匹配的合同
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
            groups.map((g) => (
              <section key={g.type} className="mt-6 first-of-type:mt-2.5">
                <div className="sticky top-[54px] z-[5] -mt-px bg-[linear-gradient(to_bottom,var(--background)_80%,transparent)] px-0.5 pt-1.5 pb-[7px]">
                  <b className="text-[11px] font-[650] tracking-[0.09em] text-muted-foreground uppercase">{g.type}</b>
                  <span className="ml-2.5 text-[11px] text-muted-foreground/60 tabular-nums">{g.deals.length}</span>
                </div>
                <div className="mt-0.5 overflow-hidden rounded-[14px] border border-border bg-card shadow-sm">
                  {g.deals.map((d) => (
                    <DealRow key={d.id} deal={d} onOpenSheet={openSheet} onDetailNotReady={detailNotReady} />
                  ))}
                </div>
              </section>
            ))
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
      </PageFade>

      <DealSheet
        deal={sheet.deal}
        open={sheet.open}
        onOpenChange={(open) => !open && setSheet((s) => ({ ...s, open: false }))}
      />
    </div>
  )
}
