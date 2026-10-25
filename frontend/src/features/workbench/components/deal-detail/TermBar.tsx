import { useMemo } from 'react'

import { buildTermTimeline, termHeadline, termTone } from './term-timeline'

/**
 * 服务期进度条：把「还剩多少时间」和「这一年服务了多少事」画到同一条轴上。
 *
 * **为什么不该只是两行文字**：常法顾问页面最该回答的问题是「服务期还剩多久、
 * 这一年忙不忙」。`2025-10-22 → 2026-10-21` 这种要读两遍才反应过来；一条
 * 进度条一眼就知道。更重要的是**事项刻度联动**：事项（合同/开庭/期限）按日
 * 落在轴上，刻度密说明那个月忙，空档说明服务空转——律师自己也能看出要不要
 * 催客户。
 */
export function TermBar({
  from,
  to,
  today,
  eventDates,
}: {
  from: string
  to: string
  /** 今天（yyyy-mm-dd）：由页面传，便于测试与跨天刷新 */
  today: string
  /** 事项日期（yyyy-mm-dd），画成轴上的刻度 */
  eventDates?: string[]
}) {
  const t = useMemo(
    () => buildTermTimeline({ from, to, today, eventDates }),
    [from, to, today, eventDates],
  )
  if (!t) return null

  const tone = termTone(t)
  const fillCls =
    tone === 'over' ? 'bg-status-red' : tone === 'warn' ? 'bg-status-yellow' : 'bg-foreground/70'
  const headCls =
    tone === 'over' ? 'text-status-red' : tone === 'warn' ? 'text-status-yellow' : 'text-foreground'

  return (
    <div className="rounded-[12px] border border-border bg-card px-5 pb-4 pt-3.5 shadow-sm">
      <div className="mb-2.5 flex items-baseline gap-2.5">
        <b className="text-[14px] font-[680]">服务期</b>
        <span className="text-[12px] tabular-nums text-muted-foreground">
          {t.start} → {t.end}
        </span>
        <span className="text-[11.5px] text-muted-foreground/70">共 {t.totalDays} 天</span>
        <span className={'ml-auto text-[12.5px] font-[650] tabular-nums ' + headCls}>
          {termHeadline(t.daysLeft)}
        </span>
      </div>

      {/* 轴：底轨 + 已流逝 + 预警区 + 事项刻度 + 今天标记 */}
      <div className="relative h-[8px] rounded-full bg-secondary" role="img"
        aria-label={`服务期 ${t.start} 至 ${t.end}，${termHeadline(t.daysLeft)}`}
      >
        <span
          className={'absolute inset-y-0 left-0 rounded-full ' + fillCls}
          style={{ width: `${t.progress * 100}%` }}
        />

        {/* 预警区：最后 20% 斜纹，提示「快到期了」而不只靠颜色 */}
        {t.warnFrom !== null && t.progress < 1 && (
          <span
            className="absolute -top-[2px] -bottom-[2px] rounded-[3px] border border-dashed border-border"
            style={{
              left: `${t.warnFrom * 100}%`,
              width: `${(1 - t.warnFrom) * 100}%`,
              backgroundImage:
                'repeating-linear-gradient(-45deg, oklch(0.96 0 0), oklch(0.96 0 0) 3px, transparent 3px, transparent 6px)',
            }}
            title="到期前 20% 区间"
          />
        )}

        {/* 事项刻度：越密说明那个阶段越忙（这也是「服务事项替代文件夹」的落点） */}
        {t.ticks.map((tick) => (
          <span
            key={tick.ratio}
            className={
              'absolute top-1/2 size-[7px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-card ' +
              (tick.today ? 'bg-status-red' : 'bg-foreground/45')
            }
            style={{ left: `${tick.ratio * 100}%` }}
            title={`${tick.count} 项事项`}
          />
        ))}

        {/* 今天：竖线压在轴上，比刻度更醒目 */}
        {t.progress > 0 && t.progress < 1 && (
          <span
            className="absolute -top-[4px] -bottom-[4px] w-[2.5px] -translate-x-1/2 rounded-full bg-status-red"
            style={{ left: `${t.progress * 100}%` }}
          />
        )}
      </div>

      <div className="relative mt-1.5 flex justify-between text-[11px] tabular-nums text-muted-foreground/70">
        <span>{t.start}</span>
        {t.ticks.length > 0 && (
          <span className="text-muted-foreground">{t.ticks.length} 个服务日</span>
        )}
        <span>{t.end}</span>
      </div>
    </div>
  )
}
