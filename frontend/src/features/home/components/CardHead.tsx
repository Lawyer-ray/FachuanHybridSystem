import { Link } from 'react-router'
import { ChevronRight } from 'lucide-react'

import { COUNT_PILL } from '../ui'

/** 右栏卡片的头部：标题 + 计数小丸（今日卡 / 收件箱共用）。
 *
 *  moreHref 给「查看全部」入口——首页这张卡只展示最近几条，不给出口的话
 *  用户看到第 6 条就断了（收件箱实际有几百条）。 */
export function CardHead({
  title,
  count,
  moreHref,
  moreLabel = '查看全部',
}: {
  title: string
  count: string
  moreHref?: string
  moreLabel?: string
}) {
  return (
    <div className="flex items-center gap-2.5 px-4 pt-[15px] pb-1">
      <b className="text-[13.5px] font-semibold">{title}</b>
      <span className={COUNT_PILL}>{count}</span>
      {moreHref && (
        <Link
          to={moreHref}
          className="ml-auto flex items-center gap-0.5 rounded-[6px] px-1 py-[2px] text-[11px] text-muted-foreground no-underline transition-colors hover:text-foreground"
        >
          {moreLabel}
          <ChevronRight className="h-3 w-3" aria-hidden />
        </Link>
      )}
    </div>
  )
}
