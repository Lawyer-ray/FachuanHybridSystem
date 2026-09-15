import { useMemo } from 'react'
import { FileText, ImageIcon, Paperclip } from 'lucide-react'
import { format, isToday, isYesterday } from 'date-fns'
import { zhCN } from 'date-fns/locale'
import type { InboxMessage } from '../types'
import { cn } from '@/lib/utils'

function timeLabel(iso: string): string {
  try {
    const d = new Date(iso)
    if (isToday(d)) return '今天 ' + format(d, 'HH:mm')
    if (isYesterday(d)) return '昨天 ' + format(d, 'HH:mm')
    return format(d, 'MM-dd', { locale: zhCN })
  } catch {
    return iso
  }
}

export function PackCard({
  pack,
  onOpen,
}: {
  pack: InboxMessage
  onOpen: () => void
}) {
  const kindHint = useMemo(() => {
    // 列表接口不含附件明细，用附件数量给一个「材料份数」弱信息
    if (pack.attachment_count <= 0) return '空材料包'
    return `${pack.attachment_count} 份附件`
  }, [pack.attachment_count])

  return (
    <article
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen()
        }
      }}
      className="group cursor-pointer rounded-[13px] border border-border bg-card transition-all hover:-translate-y-px hover:border-zinc-300 hover:shadow-md"
    >
      <div className="relative flex h-[150px] items-center justify-center overflow-hidden border-b border-border bg-secondary px-4">
        {/* 纸张堆叠缩略图 */}
        <div className="flex items-center">
          {pack.attachment_count === 0 ? (
            <div className="flex h-24 w-16 items-center justify-center rounded-[5px] border border-border bg-background text-muted">
              <Paperclip className="h-5 w-5" />
            </div>
          ) : (
            Array.from({ length: Math.min(pack.attachment_count, 3) }).map((_, idx) => (
              <div
                key={idx}
                className={cn(
                  'relative flex h-[104px] flex-col gap-1.5 rounded-[5px] border border-border bg-card p-3 shadow-sm',
                  idx > 0 && '-ml-10',
                )}
                style={{ zIndex: idx + 1 }}
              >
                {idx === 0 ? (
                  <span className="mb-1 h-[7px] w-[60%] rounded-[2px] bg-zinc-300" />
                ) : null}
                <span className="block h-[2px] w-full rounded-[1px] bg-zinc-200" />
                <span className="block h-[2px] w-[74%] rounded-[1px] bg-zinc-200" />
                <span className="block h-[2px] w-[88%] rounded-[1px] bg-zinc-200" />
              </div>
            ))
          )}
        </div>

        <span className="tag-src absolute right-3 top-2.5 rounded-full border border-zinc-200 bg-white/90 px-2 py-0.5 text-[10.5px] text-secondary-foreground">
          刚收进来
        </span>
        <span className="absolute left-3 top-2.5 flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10.5px] text-amber-700">
          待拆
        </span>
      </div>

      <div className="px-4 pt-3">
        <div className="flex items-baseline gap-2">
          <h3 className="min-w-0 flex-1 truncate text-sm font-medium tracking-tight">
            {pack.subject || `材料包 ${pack.id}`}
          </h3>
        </div>
        <div className="mt-1 flex items-center gap-2 text-xs text-secondary-foreground">
          {kindHint}
          <span className="h-[3px] w-[3px] rounded-full bg-zinc-300" />
          <span>{timeLabel(pack.received_at)}</span>
        </div>
      </div>

      <div className="flex items-center gap-2 px-4 pb-3.5 pt-3 text-[11.5px] text-muted-foreground">
        <FileText className="h-3.5 w-3.5" />
        <span className="truncate">收件箱材料 · 源：{pack.source_name}</span>
        <span className="ml-auto flex items-center gap-1">
          <ImageIcon className="h-3.5 w-3.5" />
          {pack.attachment_count}
        </span>
      </div>
    </article>
  )
}
