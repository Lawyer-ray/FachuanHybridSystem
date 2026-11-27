import { Skeleton } from '@/components/shared/Skeleton'

import { DEAL_ROW_SHELL } from './DealRow'

/**
 * 项目列表的骨架行（首屏加载态）。
 *
 * ## 为什么是「照着真行画」而不是一块灰板
 *
 * 真列表是 50 行（约 3300px），期间整页只有一块 py-[90px] 的转圈（约 150px 高）：
 * 数据到位瞬间滚动条猛现、视线失焦。（该接口修掉后端 N+1 与 traceback 刷屏后
 * 实测 p50 104ms / p95 153ms，配合 300ms 延迟门控，骨架只在长尾上出现。）骨架的唯一价值就是把这个跳动
 * 抹平，所以容器必须和真行**同源**：直接复用 `DEAL_ROW_SHELL`，
 * 内层照抄「状态点 / min-w-0 flex-1 中栏 / 右对齐金额列 / 27px 双按钮位」。
 *
 * ## 高度怎么算的（主流真行：单行客户名 + 类型标签 + 金额 + 到期）
 *
 *   py-3 上下 24
 *   + 标题 14.5px × 1.45 = 21.025（真行 `text-[14.5px] leading-[1.45]`）
 *   + mt-[3px]
 *   + 副行 18（真行副行是 flex，其中类型标签 10px × 1.6 + 上下描边 2 = 18 最高）
 *   = 66.025px（+ 1px 下边框）
 * 占位块一律写成「字号 + 行高倍数」（`text-[14.5px] h-[1.45em]`）而不是手猜
 * `h-4` / `h-5`：真行改字号时骨架跟着变，不会两边各改各的。
 *
 * ## 卡片外框为什么也在这里
 *
 * 真列表在 `<section className="mt-2.5"><div className="rounded-[14px] border …">`
 * 里。骨架只换行不换框的话，数据到位时描边 / 圆角 / 阴影凭空出现、整块内容
 * 位移 1px 再闪一下——正是要消除的那种跳。
 */
export function DealRowSkeleton({ count }: { count: number }) {
  return (
    <section className="mt-2.5">
      <div className="overflow-hidden rounded-[14px] border border-border bg-card shadow-sm">
        {Array.from({ length: count }, (_, i) => (
          <div key={i} data-skeleton-row="deal" className={DEAL_ROW_SHELL}>
            {/* 状态点位：真行是 7px 圆点 */}
            <Skeleton className="size-[7px] flex-none rounded-full" />
            <div className="min-w-0 flex-1">
              {/* 标题行：14.5px × 1.45 = 21.025px */}
              <Skeleton className="h-[1.45em] w-[58%] text-[14.5px]" />
              <div className="mt-[3px] flex items-center gap-2">
                {/* 类型标签胶囊：10px × 1.6 + 上下描边 2 = 18px（副行高度的决定项） */}
                <Skeleton className="h-[18px] w-12 flex-none rounded-[5px]" />
                {/* 副行正文：11.5px × 1.5（preflight 继承行高）= 17.25px */}
                <Skeleton className="h-[1.5em] w-[42%] text-[11.5px]" />
              </div>
            </div>
            {/* 金额 / 到期：右对齐两行，间距 gap-0.5（2px）+ 21 + 16.5 = 39.5px */}
            <div className="flex flex-none flex-col items-end gap-0.5">
              <Skeleton className="h-[1.5em] w-[68px] text-[14px]" />
              <Skeleton className="h-[1.5em] w-10 text-[11px]" />
            </div>
            {/* 预览 / 详情双按钮位：真行 27px 见方 */}
            <div className="flex flex-none gap-[5px]">
              <Skeleton className="size-[27px] rounded-[8px]" />
              <Skeleton className="size-[27px] rounded-[8px]" />
            </div>
          </div>
        ))}
      </div>
    </section>
  )
}
