import { useCallback, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'

import { AppNavbar } from '@/components/shared/AppNavbar'
import { PageFade } from '@/components/shared/PageFade'
import { filterDeals, groupDeals, sortDeals } from '../domain'
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
export function WorkbenchPage() {
  const { deals, isLoading, error, refetch } = useWorkbenchData()
  const [filter, setFilter] = useState<WorkbenchFilter>({ status: 'active', cat: '', fee: '', q: '' })
  const [sheetDeal, setSheetDeal] = useState<WorkbenchDeal | null>(null)

  const notify = useCallback((msg: string) => toast.info(msg), [])
  const detailNotReady = useCallback(() => toast.info('详情页正在开发中（右键行 = 快速预览）'), [])

  const visible = useMemo(() => sortDeals(filterDeals(deals, filter)), [deals, filter])
  const groups = useMemo(() => groupDeals(visible, !!filter.cat), [visible, filter.cat])
  const activeCount = useMemo(() => deals.filter((d) => d.status === 'active').length, [deals])
  const caseCount = useMemo(() => deals.reduce((n, d) => n + d.cases.length, 0), [deals])

  return (
    <div className="min-h-screen bg-background">
      <AppNavbar onNotify={notify} />
      <PageFade>
        <main className="mx-auto max-w-[1460px] px-7 pt-[30px] pb-[110px]">
          {/* 页头单行：标题 + 摘要 + 搜索/筛选/chips */}
          <div className="mb-3.5 flex flex-wrap items-center gap-4">
            <h1 className="text-[21px] font-[750] tracking-[-0.02em]">办案</h1>
            {!isLoading && !error && deals.length > 0 && (
              <span className="text-xs whitespace-nowrap text-muted-foreground tabular-nums">
                <b className="font-semibold text-secondary-foreground">{deals.length}</b> 个合同 ·{' '}
                <b className="font-semibold text-secondary-foreground">{activeCount}</b> 在办 ·{' '}
                <b className="font-semibold text-secondary-foreground">{caseCount}</b> 个案件
              </span>
            )}
            <FilterBar deals={deals} filter={filter} onChange={setFilter} />
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
          ) : visible.length === 0 ? (
            deals.length === 0 ? (
              <div className="py-[90px] text-center text-[13px] text-muted-foreground">还没有合同数据</div>
            ) : (
              <div className="py-[90px] text-center text-[13px] text-muted-foreground">
                没有匹配的合同
                <button
                  type="button"
                  className="ml-1.5 cursor-pointer underline underline-offset-3"
                  onClick={() => setFilter({ status: 'active', cat: '', fee: '', q: '' })}
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
                    <DealRow key={d.id} deal={d} onOpenSheet={setSheetDeal} onDetailNotReady={detailNotReady} />
                  ))}
                </div>
              </section>
            ))
          )}
        </main>
      </PageFade>

      <DealSheet deal={sheetDeal} onOpenChange={(open) => !open && setSheetDeal(null)} />
    </div>
  )
}
