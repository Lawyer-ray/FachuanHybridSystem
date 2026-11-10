import { Link } from 'react-router'
import { ChevronRight } from 'lucide-react'

/** 面板标题行的小胶囊（计数）—— 只被本组件使用，故就近定义不分发到 feature */
const COUNT_PILL =
  'rounded-[99px] border border-border bg-secondary px-[8px] py-[1px] text-[11px] font-semibold text-muted-foreground'

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
  /** 计数小丸文本。省略/空串时**整颗胶囊不渲染**——空胶囊会被误读成「0 条」。
   *  合并卡（款项+发票）不在这里给数字：两个分组的条数各自列在组标题旁。 */
  count?: string
  moreHref?: string
  moreLabel?: string
}) {
  return (
    <div className="flex items-center gap-2.5 px-4 pt-[15px] pb-1">
      <b className="text-[13.5px] font-semibold">{title}</b>
      {count ? <span className={COUNT_PILL}>{count}</span> : null}
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
