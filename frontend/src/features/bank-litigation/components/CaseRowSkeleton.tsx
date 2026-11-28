import { Skeleton } from '@/components/shared/Skeleton'

import { CASE_ROW_SHELL, CaseListHeader } from './CaseRow'

/**
 * 案件列表的骨架行（首屏加载态）。
 *
 * ## 为什么是「照着真行画」而不是一块灰板
 *
 * 真列表是 50 行，而转圈的 LoadingBlock 只占 ~100px：数据到位瞬间滚动条猛现、
 * 视线失焦。骨架的唯一价值是把这一跳抹平，所以容器必须和真行**同源**——
 * 直接复用 `CASE_ROW_SHELL`（含列宽，见 `CASE_ROW_COLUMNS`），内层照抄
 * 「min-w-0 案件列（名 + 案由两行）/ 阶段 / 状态徽章 / 案号 / 右对齐金额 / 箭头」。
 *
 * ## 高度怎么算的
 *
 *   py-2.5 上下 20
 *   + 案件名 13px × 1.5 = 19.5
 *   + mt-0.5 = 2
 *   + 案由 11px × 1.5 = 16.5
 *   = 58px（+ 1px 下边框）
 * 占位块一律写成「字号 + 行高倍数」（`text-[13px] h-[1.5em]`）而不是手猜
 * `h-4` / `h-5`：真行改字号时骨架跟着变，不会两边各改各的。
 *
 * ## 卡片外框为什么也在这里
 *
 * 真列表在 `rounded-[10px] border border-border bg-card` 的卡里。骨架只换行不换框
 * 的话，数据到位时描边 / 圆角凭空出现、整块内容位移一下——正是要消除的那种跳。
 *
 * 表头也画：直接渲染真组件 `CaseListHeader`（同一个 `CASE_ROW_COLUMNS`），
 * 所以骨架与真列表是**同一棵树**换皮，高度天然一致。表头是静态文案，不需要灰块。
 */
export function CaseRowSkeleton({ count }: { count: number }) {
  return (
    <div className="overflow-hidden rounded-[10px] border border-border bg-card">
      <CaseListHeader />
      {Array.from({ length: count }, (_, i) => (
        <div key={i} data-skeleton-row="case" className={CASE_ROW_SHELL}>
          <div className="min-w-0">
            {/* 案件名：13px × 1.5 = 19.5px */}
            <Skeleton className="h-[1.5em] w-[58%] text-[13px]" />
            <div className="mt-0.5">
              {/* 案由：11px × 1.5 = 16.5px */}
              <Skeleton className="h-[1.5em] w-[42%] text-[11px]" />
            </div>
          </div>
          {/* 阶段：12px 单行 */}
          <Skeleton className="h-[1.5em] w-8 text-[12px]" />
          {/* 状态徽章：11px × 1.6 + 上下描边 2 = 19.6px，圆角 4px */}
          <Skeleton className="h-5 w-12 rounded-[4px]" />
          {/* 案号：11.5px 单行 */}
          <Skeleton className="h-[1.5em] w-20 text-[11.5px]" />
          {/* 标的额：右对齐（真行是 text-right，块级占位要自己靠右） */}
          <Skeleton className="h-[1.5em] w-16 justify-self-end text-[12px]" />
          {/* 箭头位：真行是 size-3.5 图标 */}
          <Skeleton className="size-3.5 rounded" />
        </div>
      ))}
    </div>
  )
}
