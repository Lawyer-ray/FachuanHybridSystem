/**
 * 常年顾问 · 服务配额卡
 *
 * 常法合同卖的是「一年 20 小时/月」，所以这一页最该回答的是三个数字：
 * **服务期还剩多久**、**每个月实际忙到什么程度**、**本月配额是不是要爆了**。
 * 三样都画成条/柱，律师扫一眼就知道要不要去谈续签。
 *
 * 均为展示数据（`DEMO_NL3_*`），不参与任何真实业务判断；口径计算在 advisor-domain。
 */

import { CalendarClock, Gauge } from 'lucide-react'

import { cn } from '@/lib/utils'

import {
  DEMO_NL3_MONTHLY_HOURS,
  DEMO_NL3_QUOTA_POLICY,
  DEMO_NL3_SERVICE_STATS,
} from '../../demo-nonlit'
import { Card } from '../../ui'
import { monthBars, quotaLineRatio, quotaTone, quotaUsage, serviceTermProgress } from './advisor-domain'

const TONE_TEXT = {
  green: 'text-status-green',
  yellow: 'text-status-yellow',
  red: 'text-status-red',
} as const

const TONE_FILL = {
  green: 'bg-status-green',
  yellow: 'bg-status-yellow',
  red: 'bg-status-red',
} as const

const TONE_BOX = {
  green: 'border-status-green/40 bg-status-green-bg/60',
  yellow: 'border-status-yellow/40 bg-status-yellow-bg/60',
  red: 'border-status-red/40 bg-status-red-bg/60',
} as const

export function AdvisorQuotaCard() {
  const s = DEMO_NL3_SERVICE_STATS
  const termPct = Math.round(serviceTermProgress() * 100)
  const usage = quotaUsage(s.totalHours, s.monthlyQuota)
  const tone = quotaTone(usage)
  const bars = monthBars(DEMO_NL3_MONTHLY_HOURS, s.monthlyQuota)
  const quotaLine = quotaLineRatio(DEMO_NL3_MONTHLY_HOURS, s.monthlyQuota)
  const peak = Math.max(...DEMO_NL3_MONTHLY_HOURS.map((m) => m.hours))
  const peakMonth = DEMO_NL3_MONTHLY_HOURS.find((m) => m.hours === peak)?.month ?? ''
  const overMonths = DEMO_NL3_MONTHLY_HOURS.filter((m) => m.hours > s.monthlyQuota).length

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex items-baseline gap-2">
        <h3 className="text-[13px] font-[620]">服务配额</h3>
        <span className="text-[11px] text-muted-foreground">服务期进度 · 月度工时 · 配额预警</span>
        <span className={cn('ml-auto text-[12px] font-[650] tabular-nums', TONE_TEXT[tone])}>
          本月 {s.totalHours}h / {s.monthlyQuota}h（{usage}%）
        </span>
      </div>

      {/* ① 服务期进度 */}
      <div className="mt-3">
        <div className="mb-1 flex items-baseline gap-2 text-[11px]">
          <CalendarClock className="size-3 flex-none text-muted-foreground" />
          <span className="font-medium">年度服务期</span>
          <span className="tabular-nums text-muted-foreground">
            已用 {s.usedDays} 天 / 共 {s.contractDays} 天
          </span>
          <span className="ml-auto tabular-nums text-muted-foreground">
            {s.from} → {s.to}
          </span>
        </div>
        <div
          className="relative h-[9px] overflow-hidden rounded-full bg-secondary"
          role="img"
          aria-label={`年度服务期已用 ${s.usedDays} 天，共 ${s.contractDays} 天`}
        >
          <div
            className="h-full rounded-full bg-foreground/70 transition-[width] duration-500"
            style={{ width: `${termPct}%` }}
          />
          {/* 今天：与 TermBar 同口径的红竖线 */}
          <span
            className="absolute inset-y-0 w-[2px] bg-status-red"
            style={{ left: `calc(${termPct}% - 1px)` }}
          />
        </div>
        <div className="mt-1 flex justify-between text-[10px] tabular-nums text-muted-foreground">
          <span>{termPct}%</span>
          <span>剩 {s.remainDays} 天</span>
        </div>
      </div>

      {/* ② 月度工时柱状图（12 个月，纯 div；配额线画在柱子上方的数字行下方） */}
      <div className="mt-3">
        <div className="mb-1 flex items-baseline gap-2 text-[11px]">
          <Gauge className="size-3 flex-none text-muted-foreground" />
          <span className="font-medium">月度工时</span>
          <span className="text-muted-foreground">峰值 {peak}h（{peakMonth.slice(5)} 月）</span>
          <span className="ml-auto text-muted-foreground">
            {overMonths > 0 ? `超配额 ${overMonths} 个月` : '均在配额内'} · 虚线为 {s.monthlyQuota}h 上限
          </span>
        </div>
        <div className="relative flex h-[92px] items-end gap-[3px] rounded-[8px] border border-border-light bg-background px-2 pt-2 pb-0">
          {/* 配额线：与柱子同一坐标系（高度比例同源） */}
          <span
            className="pointer-events-none absolute right-2 left-2 border-t border-dashed border-status-yellow/70"
            style={{ bottom: `${quotaLine * 100}%` }}
            title={`每月配额 ${s.monthlyQuota}h`}
          />
          {bars.map((b) => (
            <div key={b.month} className="group relative flex h-full min-w-0 flex-1 flex-col justify-end">
              <div
                className={cn(
                  'w-full rounded-t-[2px] transition-[height] duration-500',
                  b.over ? 'bg-status-yellow' : 'bg-foreground/45',
                )}
                style={{ height: `${b.ratio * 100}%` }}
                title={`${b.month} · ${b.hours}h${b.over ? '（超配额）' : ''}`}
              />
              <div className="mt-[2px] flex-none text-center text-[8.5px] leading-none tabular-nums text-muted-foreground">
                {b.month.slice(5)}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* ③ 配额预警 */}
      <div className={cn('mt-3 rounded-[9px] border px-3 py-2', TONE_BOX[tone])}>
        <div className="flex items-center gap-2">
          <span className={cn('text-[11.5px] font-[620]', TONE_TEXT[tone])}>
            {usage >= DEMO_NL3_QUOTA_POLICY.exceedPct
              ? '配额已超用'
              : usage >= DEMO_NL3_QUOTA_POLICY.warnPct
                ? `配额预警：已用 ${usage}%`
                : '配额正常'}
          </span>
          <span className="text-[10.5px] text-muted-foreground">
            阈值 {DEMO_NL3_QUOTA_POLICY.warnPct}% 标黄 / {DEMO_NL3_QUOTA_POLICY.exceedPct}% 标红
          </span>
          <span className="ml-auto text-[10.5px] tabular-nums text-muted-foreground">
            剩余 {Math.max(0, Math.round((s.monthlyQuota - s.totalHours) * 10) / 10)}h
          </span>
        </div>
        <div className="mt-1.5 h-[6px] overflow-hidden rounded-full bg-background">
          <div
            className={cn('h-full rounded-full transition-[width] duration-500', TONE_FILL[tone])}
            style={{ width: `${Math.min(100, usage)}%` }}
          />
        </div>
        <p className="mt-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
          本月 {s.totalHours}h 已用 {usage}% 配额；按当前节奏，本季度末累计工时将超合同约定，建议在续签时把月配额上调到{' '}
          {Math.round(s.monthlyQuota * 1.5)}h。
        </p>
      </div>
    </Card>
  )
}
