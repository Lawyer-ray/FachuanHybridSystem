import { memo, useMemo } from 'react'
import { FileText, ImageIcon, Layers } from 'lucide-react'
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

function typeIcon(k: string) {
  if (k === 'photo') return <ImageIcon className="h-4 w-4" />
  if (k === 'office') return <Layers className="h-4 w-4" />
  return <FileText className="h-4 w-4" />
}

export const PackCard = memo(function PackCard({
  pack,
  finished,
  leaving,
  onOpen,
  onReject,
  onAccept,
}: {
  pack: InboxMessage
  /** 拆分与归类是否全部完成（segs>0 且 named===segs）——决定归案按钮是否可用 */
  finished: boolean
  /** 离场方向：不接=left / 归案=right（触发动画后由父级移除） */
  leaving?: 'left' | 'right' | null
  onOpen: () => void
  onReject: () => void
  onAccept: () => void
}) {
  const pct = pack.segs ? Math.round((pack.named / pack.segs) * 100) : 0
  const kinds = pack.types ?? []
  const restUnclassified = pack.segs - kinds.length

  const compose = useMemo(() => {
    if (!pack.compose) return `${pack.mats} 个源文件`
    return pack.compose
  }, [pack.compose])

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
      className={cn(
        'mp-packet group cursor-pointer rounded-[13px] border border-border bg-card transition-all hover:-translate-y-px hover:border-zinc-300 hover:shadow-md',
        leaving === 'right' && 'leave-right',
        leaving === 'left' && 'leave-left',
      )}
    >
      {/* 已归案印章 */}
      <span
        className={cn('mp-stamp mp-stamp-mark', pack.status === 'done' && 'stamped')}
        style={{ transform: pack.status === 'done' ? 'rotate(-14deg) scale(1)' : undefined }}
      >
        已归案
      </span>

      {/* 缩略图带 + 来源标签 */}
      <div className="thumbband relative flex h-[148px] items-center justify-center overflow-hidden border-b border-border bg-secondary px-4">
        <span
          className={cn(
            'absolute left-3 top-2.5 flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10.5px]',
            pack.segs === 0
              ? 'border-zinc-200 bg-zinc-50 text-secondary-foreground'
              : finished
                ? 'border-green-200 bg-green-50 text-green-700'
                : 'border-amber-200 bg-amber-50 text-amber-700',
          )}
        >
          {pack.segs === 0
            ? '未打开'
            : finished
              ? '已归类'
              : `${pack.segs - pack.named} 份未归类`}
        </span>
        <span className="tag-src absolute right-3 top-2.5 flex items-center gap-1 rounded-full border border-zinc-200 bg-white/90 px-2 py-0.5 text-[10.5px] text-secondary-foreground">
          {typeIcon(pack.source_type === 'manual_upload' ? 'office' : 'pdf')}
          {pack.source_name || '收件箱'}
        </span>

        {/* 纸堆缩略 */}
        <div className="flex items-center">
          {pack.mats <= 0 ? (
            <div className="flex h-24 w-16 items-center justify-center rounded-[5px] border border-border bg-background text-muted">
              <FileText className="h-5 w-5" />
            </div>
          ) : (
            Array.from({ length: Math.min(pack.mats || 1, 3) }).map((_, idx) => (
              <div
                key={idx}
                className={cn(
                  'relative flex h-[104px] w-[70px] flex-col gap-1.5 rounded-[5px] border border-border bg-card p-3 shadow-sm',
                  idx > 0 && '-ml-9',
                )}
                style={{ zIndex: idx + 1 }}
              >
                {idx === 0 && <span className="mb-1 h-[7px] w-[60%] rounded-[2px] bg-zinc-300" />}
                <span className="block h-[2px] w-full rounded-[1px] bg-zinc-200" />
                <span className="block h-[2px] w-[74%] rounded-[1px] bg-zinc-200" />
                <span className="block h-[2px] w-[88%] rounded-[1px] bg-zinc-200" />
              </div>
            ))
          )}
        </div>
        {(pack.mats ?? 0) > 3 && (
          <span className="absolute bottom-2 right-3 rounded-full bg-foreground/80 px-2 py-0.5 text-[10.5px] text-background">
            +{pack.mats - 3}
          </span>
        )}
      </div>

      {/* 标题 + 事实链 + 进度条 */}
      <div className="px-4 pt-3">
        <div className="flex items-baseline gap-2">
          <h3 className="min-w-0 flex-1 truncate text-sm font-medium tracking-tight">
            {pack.subject || `材料包 ${pack.id}`}
          </h3>
          <span className="flex-none text-[11px] tabular-nums text-muted-foreground">
            {pack.pages > 0 ? `${pack.pages} 页` : pack.mats > 0 ? `${pack.mats} 个文件` : ''}
          </span>
        </div>

        <div className="mt-1.5 flex min-h-[20px] flex-wrap items-center gap-x-1.5 gap-y-1 text-[11.5px]">
          {pack.segs === 0 ? (
            <span className="text-muted-foreground">还没拆这份材料包</span>
          ) : kinds.length === 0 ? (
            <span className="text-muted-foreground">{pack.segs} 份材料待归类</span>
          ) : (
            <>
              {kinds.map((t, i) => (
                <span key={i}>
                  {i > 0 && <span className="mx-1 h-[3px] w-[3px] rounded-full bg-zinc-300" />}
                  <b className="font-medium text-foreground">{t}</b>
                </span>
              ))}
              {restUnclassified > 0 && (
                <>
                  <span className="mx-1 h-[3px] w-[3px] rounded-full bg-zinc-300" />
                  <span className="text-muted-foreground">+{restUnclassified} 份未归类</span>
                </>
              )}
            </>
          )}
        </div>

        <div
          className={cn(
            'mt-2 h-[5px] w-full overflow-hidden rounded-full bg-zinc-200/80',
            finished && 'bg-green-100',
          )}
        >
          <i
            className={cn('block h-full rounded-full', finished ? 'bg-green-500' : 'bg-amber-500')}
            style={{ width: `${finished ? 100 : pct}%` }}
          />
        </div>
      </div>

      {/* 底部元信息 + 操作 */}
      <div
        className="flex items-center gap-2 px-4 pb-3.5 pt-3 text-[11.5px] text-muted-foreground"
        onClick={(e) => e.stopPropagation()}
      >
        <span className="min-w-0 truncate">
          {compose}
          <span className="mx-1.5 h-[3px] w-[3px] inline-block rounded-full bg-zinc-300 align-middle" />
          {timeLabel(pack.received_at)}
        </span>
        <span className="ml-auto flex flex-none items-center gap-1.5">
          <button
            type="button"
            onClick={onReject}
            title="不接：已归档留痕，未建案"
            className="flex h-7 items-center gap-1 rounded-md border border-border bg-card px-2 text-[12px] text-secondary-foreground transition-colors hover:border-zinc-300 hover:bg-secondary"
          >
            不接
          </button>
          <button
            type="button"
            onClick={onAccept}
            disabled={!finished}
            title={finished ? '归案：绑定案件后进入办案流程' : '先完成拆分与归类'}
            className={cn(
              'flex h-7 items-center gap-1 rounded-md border px-2 text-[12px] transition-colors',
              finished
                ? 'border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100'
                : 'cursor-not-allowed opacity-40',
            )}
          >
            归案
          </button>
        </span>
      </div>
    </article>
  )
})
