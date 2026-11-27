import { Skeleton } from '@/components/shared/Skeleton'

import { INBOX_ROW_SHELL } from './InboxRowItem'

/**
 * 收件箱列表的骨架行（首屏加载态）。
 *
 * 照 `InboxRowItem` 的盒子画：行首 32px 来源图标位 + 中栏两行（主题 13px×1.35、
 * 副行徽章 10px×1.5 + 上下 padding/描边 = 19px）+ 右侧时间与附件胶囊列。
 * 主流真行（单行主题 + 有附件）高度：
 *   py-3 24 + 主题 17.55 + mt-0.5 2 + 副行 19 = 62.55px（+ 1px 分隔线）
 * 占位块写成「字号 + 行高倍数」（`text-[13px] h-[1.35em]`）而不是手猜 h-4/h-5，
 * 真行改字号时骨架跟着变。
 *
 * 方块与真行之间用 `divide-y divide-border/70` 画出同一道分隔线（真列表的
 * 分组也是这个类），否则骨架行是连成一片的灰、数据到位时多出 7 条线。
 */
export function InboxRowSkeleton({ count }: { count: number }) {
  return (
    <ul className="divide-y divide-border/70">
      {Array.from({ length: count }, (_, i) => (
        <li key={i} data-skeleton-row="inbox" className={INBOX_ROW_SHELL}>
          {/* 来源图标位：真行 mt-0.5 + 32px 圆角方块（含 1px 描边，border-box） */}
          <Skeleton className="mt-0.5 h-8 w-8 flex-none rounded-[9px]" />
          <span className="min-w-0 flex-1">
            {/* 主题行：13px × 1.35 = 17.55px */}
            <Skeleton className="h-[1.35em] w-[62%] text-[13px]" />
            <span className="mt-0.5 flex items-center gap-1.5">
              {/* 来源徽章：10px × 1.5 + py-px 2 + 上下描边 2 = 19px（副行的决定项） */}
              <Skeleton className="h-[19px] w-12 flex-none rounded-[4px]" />
              {/* 发送人 / 副标题：11.5px × 1.5 = 17.25px */}
              <Skeleton className="h-[1.5em] w-[40%] text-[11.5px]" />
            </span>
          </span>
          {/* 时间 + 附件胶囊：11px × 1.5 = 16.5，gap-1，胶囊 10px × 1.5 + py-px 2 = 17 */}
          <span className="flex flex-none flex-col items-end gap-1">
            <Skeleton className="h-[1.5em] w-10 text-[11px]" />
            <Skeleton className="h-[17px] w-9 rounded-[4px]" />
          </span>
        </li>
      ))}
    </ul>
  )
}
