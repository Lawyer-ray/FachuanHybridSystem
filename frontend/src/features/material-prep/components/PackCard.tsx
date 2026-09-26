import { memo, useMemo } from 'react'
import { FileText } from 'lucide-react'
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

/** 底部元信息：拆分/归类进度 + 时间（原型 metaText，不显示构成） */
function metaText(pack: InboxMessage): string {
  const segs = pack.segs || 0
  const base = segs ? `${pack.named}/${segs} 已归类` : '待拆分'
  return `${base} · ${timeLabel(pack.received_at)}`
}

/** 缩略纸堆的一页：文档行文（标题条 + 不同宽度的正文行） */
function docPage(i: number) {
  return (
    <div
      key={i}
      className="relative flex h-[108px] w-[82px] flex-none flex-col gap-[6px] rounded-[5px] border border-border bg-card p-[14px_12px] shadow-[0_1px_3px_rgba(0,0,0,0.09)]"
      style={{ zIndex: i + 1 }}
    >
      <span className="mb-1 block h-[3px] w-[56%] rounded-[1px] bg-zinc-300" />
      <span className="block h-[2px] w-full rounded-[1px] bg-zinc-200" />
      <span className="block h-[2px] w-[88%] rounded-[1px] bg-zinc-200" />
      <span className="block h-[2px] w-[74%] rounded-[1px] bg-zinc-200" />
      <span className="block h-[2px] w-[88%] rounded-[1px] bg-zinc-200" />
      <span className="block h-[2px] w-[52%] rounded-[1px] bg-zinc-200" />
    </div>
  )
}

/** 已归案印章：小号绿色徽章（原型 stamp） */
function stamp() {
  return <span className="mp-stamp stamped mp-stamp-mark">已归案</span>
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
  const shown = useMemo(() => Math.max(1, Math.min(pack.mats || 1, 3)), [pack.mats])

  return (
    <article
      className={cn(
        'mp-packet group relative overflow-hidden rounded-[13px] border border-border bg-card transition-all hover:-translate-y-px hover:border-zinc-300 hover:shadow-md',
        leaving === 'right' && 'leave-right',
        leaving === 'left' && 'leave-left',
      )}
    >
      {/* 打开材料包的拉伸点击层：覆盖整卡、承担键盘可达，避免在 role=button 上嵌交互按钮 */}
      <button
        type="button"
        onClick={onOpen}
        aria-label={`打开材料包：${pack.subject || `材料包 ${pack.id}`}`}
        className="absolute inset-0 z-[1] cursor-pointer"
      />

      {/* 已归案印章 */}
      {pack.status === 'done' && stamp()}

      {/* 缩略图带 + 标签 */}
      <div className="relative flex h-[148px] items-center justify-center overflow-hidden border-b border-border bg-secondary px-4">
        {/* 左：拆分类标签 */}
        <span
          className={cn(
            'absolute left-[11px] top-2.5 z-[3] flex items-center gap-[5px] rounded-full border px-2 py-[2px] text-[10.5px] font-medium',
            pack.segs === 0
              ? 'border-zinc-200 bg-zinc-50 text-secondary-foreground'
              : finished
                ? 'border-green-200 bg-green-50 text-green-700'
                : 'border-amber-200 bg-amber-50 text-amber-700',
          )}
        >
          {pack.segs === 0 ? (
            '未打开'
          ) : finished ? (
            <>
              <span className="h-[5px] w-[5px] rounded-full bg-green-500" />
              已归类
            </>
          ) : (
            `${pack.segs - pack.named} 份未归类`
          )}
        </span>
        {/* 右：来源标签（无图标，纯文本） */}
        <span className="absolute right-[11px] top-2.5 z-[3] rounded-full border border-zinc-200 bg-white/90 px-2 py-[2px] text-[10.5px] font-medium text-secondary-foreground">
          {pack.source_name || '收件箱'}
        </span>

        {/* 纸堆缩略 */}
        <div className="flex items-center">
          {pack.mats <= 0 ? (
            <div className="flex h-[108px] w-[82px] items-center justify-center rounded-[5px] border border-border bg-background text-muted">
              <FileText className="h-5 w-5" />
            </div>
          ) : (
            <>
              <div className="flex items-center">
                {Array.from({ length: shown }).map((_, idx) => (
                  <div key={idx} className={idx > 0 ? '-ml-10 transition-[margin] duration-200 group-hover:-ml-[30px]' : ''}>
                    {docPage(idx)}
                  </div>
                ))}
              </div>
              {(pack.mats ?? 0) > 3 && (
                <span className="ml-[10px] flex-none rounded-full border border-border bg-card px-[9px] py-[3px] text-[11.5px] font-medium text-secondary-foreground shadow-sm">
                  +{pack.mats - 3}
                </span>
              )}
            </>
          )}
        </div>
      </div>

      {/* 标题 + 事实链 + 进度条 */}
      <div className="px-4 pt-[13px]">
        <div className="flex items-baseline gap-1">
          <h3 className="min-w-0 flex-1 truncate text-sm font-medium tracking-tight">
            {pack.subject || `材料包 ${pack.id}`}
          </h3>
          <span className="flex-none text-[12px] tabular-nums text-secondary-foreground">
            {pack.pages > 0 ? `${pack.pages} 页` : pack.mats > 0 ? `${pack.mats} 个文件` : ''}
          </span>
        </div>

        <div className="mt-1.5 flex min-h-[20px] flex-wrap items-center gap-x-1.5 gap-y-1 text-[12px] text-secondary-foreground">
          {pack.segs === 0 ? (
            <span className="text-muted-foreground">还没拆这份材料包</span>
          ) : kinds.length === 0 ? (
            <span className="text-muted-foreground">{pack.segs} 份材料待归类</span>
          ) : (
            <>
              {kinds.map((t, i) => (
                <span key={i} className="flex items-center">
                  {i > 0 && <span className="mx-1.5 h-[3px] w-[3px] rounded-full bg-zinc-300" />}
                  <b className={`font-medium ${i > 0 ? 'text-zinc-500' : 'text-foreground'}`}>{t}</b>
                </span>
              ))}
              {restUnclassified > 0 && (
                <>
                  <span className="mx-1.5 h-[3px] w-[3px] rounded-full bg-zinc-300" />
                  <span className="text-muted-foreground">+{restUnclassified} 份未归类</span>
                </>
              )}
            </>
          )}
        </div>

        <div
          className={cn(
            'mt-[11px] h-[4px] w-full overflow-hidden rounded-[2px] bg-secondary',
            finished && 'bg-green-100',
          )}
        >
          <i
            className={cn('block h-full rounded-[2px]', finished ? 'bg-green-500' : 'bg-foreground')}
            style={{ width: `${finished ? 100 : pct}%` }}
          />
        </div>
      </div>

      {/* 底部元信息 + 操作（z 抬到拉伸点击层之上，否则按钮点不到） */}
      <div
        className="relative z-[2] flex items-center gap-2 px-4 pb-[14px] pt-[13px] text-[11.5px] text-muted-foreground"
      >
        <span className="min-w-0 truncate tabular-nums">{metaText(pack)}</span>
        <span className="ml-auto flex flex-none items-center gap-[6px]">
          <button
            type="button"
            onClick={onReject}
            title="不接：已归档留痕，未建案"
            className="h-[31px] flex-none rounded-[7px] border border-transparent bg-transparent px-[13px] text-[12.5px] font-medium text-secondary-foreground transition-colors hover:border-border hover:bg-secondary hover:text-foreground"
          >
            不接
          </button>
          <button
            type="button"
            onClick={onAccept}
            disabled={!finished}
            title={finished ? '归案：绑定案件后进入办案流程' : '先完成拆分与归类'}
            className={cn(
              'h-[31px] flex-none rounded-[7px] border px-[13px] text-[12.5px] font-medium transition-colors',
              finished
                ? 'border-border bg-card text-foreground group-hover:border-foreground group-hover:bg-foreground group-hover:text-background'
                : 'cursor-not-allowed border-border bg-card text-foreground opacity-40',
            )}
          >
            归案
          </button>
        </span>
      </div>
    </article>
  )
})
