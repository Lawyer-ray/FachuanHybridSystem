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
  events,
}: {
  from: string
  to: string
  /** 今天（yyyy-mm-dd）：由页面传，便于测试与跨天刷新 */
  today: string
  /** 轴上事项：日期 + 标题（标题用于悬浮提示「这天发生了什么」） */
  events?: Array<string | { date: string; title?: string }>
}) {
  const t = useMemo(
    () => buildTermTimeline({ from, to, today, events }),
    [from, to, today, events],
  )
  if (!t) return null

  const tone = termTone(t)
  const fillCls =
    tone === 'over' ? 'bg-status-red' : tone === 'warn' ? 'bg-status-yellow' : 'bg-foreground/70'
  const headCls =
    tone === 'over' ? 'text-status-red' : tone === 'warn' ? 'text-status-yellow' : 'text-foreground'
  /** 轴上一共多少项事项（同一天的合并了刻度，但计数要按实际事项数） */
  const totalItems = t.ticks.reduce((sum, x) => sum + x.count, 0)

  return (
    <div className="rounded-[12px] border border-border bg-card px-5 pb-4 pt-3.5 shadow-sm">
      <div className="mb-2.5 flex items-baseline gap-2.5">
        <b className="text-[14px] font-[680] min-[1900px]:text-[15px]">服务期</b>
        <span className="text-[12px] tabular-nums text-muted-foreground">
          {t.start} → {t.end}
        </span>
        <span className="text-[11.5px] text-muted-foreground/70">共 {t.totalDays} 天</span>
        <span className={'ml-auto text-[12.5px] font-[650] tabular-nums ' + headCls}>
          {termHeadline(t.daysLeft)}
        </span>
      </div>

      {/* 轴：底轨 + 已流逝 + 预警区 + 事项刻度 + 今天标记 */}
      <div className="relative h-[8px] rounded-full bg-secondary min-[1900px]:h-[10px] min-[2400px]:h-[12px]" role="img"
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
              'absolute top-1/2 size-[7px] -translate-x-1/2 -translate-y-1/2 rounded-full border border-card min-[1900px]:size-[9px] ' +
              (tick.today ? 'bg-status-red' : 'bg-foreground/45')
            }
            style={{ left: `${tick.ratio * 100}%` }}
            title={tickTooltip(tick)}
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

      <div className="relative mt-1.5 flex justify-between text-[11px] tabular-nums text-muted-foreground/70 min-[1900px]:text-[11.5px]">
        <span>{t.start}</span>
        {t.ticks.length > 0 && (
          <span className="text-muted-foreground">
            {/* 原写「N 个服务日」有歧义：这是「有事项的天数」，不是服务期天数 */}
            {t.ticks.length} 天有事项 · 共 {totalItems} 项
          </span>
        )}
        <span>{t.end}</span>
      </div>
    </div>
  )
}

/**
 * 刻度的悬浮文案：`2026-06-09 · 租赁合同、交接清单`。
 *
 * 律师看轴上的点只能知道「那天有事」，看不出「什么事」——而后者才是他要在
 * 服务期里回看的。用原生 title 而不是自绘浮层：刻度只有 7px，自绘容易在
 * 轴两端被裁掉，原生提示由浏览器负责定位。
 */
function tickTooltip(tick: { date: string; count: number; titles: string[] }): string {
  const head = `${tick.date} · ${tick.count} 项`
  if (tick.titles.length === 0) return head
  // 最多列 5 条，再多就折成「等 N 项」，避免提示框长到遮住页面
  const shown = tick.titles.slice(0, 5).join('、')
  const more = tick.titles.length > 5 ? ` 等 ${tick.titles.length} 项` : ''
  return `${head}\n${shown}${more}`
}
