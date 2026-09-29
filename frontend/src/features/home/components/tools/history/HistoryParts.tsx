import { History } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * 历史弹窗共用零件：四张工具卡（法院短信 / 文档解析 / 要素式 / DOC转DOCX）
 * 的历史入口按钮、弹窗头部、分页底栏、状态徽章配色。
 */

/** 卡片头部的「历史」入口按钮（四张卡同款） */
export function HistoryButton({ title, onClick }: { title: string; onClick: () => void }) {
  return (
    <button
      type="button"
      title={title}
      className="flex h-[26px] flex-none items-center gap-1 rounded-[7px] border border-border bg-card px-2 text-[10.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground"
      onClick={onClick}
    >
      <History className="h-3 w-3" />
      历史
    </button>
  )
}

/** 分页底栏：上一页 / 页码 / 下一页 */
export function HistoryPager({
  page,
  totalPages,
  onChange,
}: {
  page: number
  totalPages: number
  onChange: (page: number) => void
}) {
  const btn =
    'rounded-[7px] px-2.5 py-1 text-[11.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40'
  return (
    <div className="flex flex-none items-center justify-between border-t border-border px-4 py-2.5">
      <button type="button" className={btn} disabled={page <= 1} onClick={() => onChange(Math.max(1, page - 1))}>
        ← 上一页
      </button>
      <span className={cn('text-[11px] text-muted-foreground')}>
        第 {page} / {totalPages} 页
      </span>
      <button
        type="button"
        className={btn}
        disabled={page >= totalPages}
        onClick={() => onChange(Math.min(totalPages, page + 1))}
      >
        下一页 →
      </button>
    </div>
  )
}

/** 历史弹窗的头部（图标 + 标题 + 计数 + 右侧筛选区），与法院短信历史弹窗同款布局 */
export function HistoryHeader({
  title,
  count,
  children,
}: {
  title: string
  count: number
  children?: React.ReactNode
}) {
  return (
    <div className="flex flex-none items-center gap-2.5 border-b border-border px-4 py-3 pr-10">
      <b className="text-[13.5px] font-semibold">{title}</b>
      <span className="text-[11px] text-muted-foreground">{count} 条</span>
      <span className="flex-1" />
      {children}
    </div>
  )
}
