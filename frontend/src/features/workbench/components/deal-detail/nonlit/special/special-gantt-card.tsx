/**
 * 关厂清盘 · 阶段甘特图（div 画的条形，不引图表库）
 *
 * 为什么不用库：这里要的只是「7 条横条 + 两侧日期」，ECharts/Recharts 打包成本
 * 几十倍于收益，而且拿不到本页的排版公制（条形要跟阶段名逐行对齐）。用百分比
 * 定位的 div 反而更准：轨道宽度随卡片自适应，条形按「开始日 / 工期占全期比例」摆。
 *
 * 一条条形表达三件事（录屏时要一眼看出问题在哪）：
 *   · 实心段 = 实际进度（进度条长度 = progress%）
 *   · 虚线尾部 = 计划内还没做完的部分
 *   · 右上角「延期 N 天」= 实际用时 − 计划工期（只有已经开工的阶段才判）
 */

import { CalendarClock, ChevronRight } from 'lucide-react'

import { cn } from '@/lib/utils'

import { DEMO_NL1_GANTT, DEMO_NONLIT_PHASES } from '../../demo-nonlit'
import { Card } from '../../ui'
import { TonePill, type Tone } from './special-bits'
import { buildGantt, ganttSummary, type GanttBar } from './special-liquidation-model'

const DRIFT_TONE: Record<GanttBar['drift'], Tone> = { late: 'red', early: 'green', ontime: 'neutral' }

const DRIFT_TEXT: Record<GanttBar['drift'], (n: number) => string> = {
  late: (n) => `延期 ${n} 天`,
  early: (n) => `提前 ${Math.abs(n)} 天`,
  ontime: () => '按计划',
}

export function SpecialGanttCard({
  onPickPhase,
}: {
  /** 点阶段条 → 打开该阶段的抽屉 */
  onPickPhase: (phaseId: string) => void
}) {
  const chart = buildGantt(DEMO_NONLIT_PHASES, DEMO_NL1_GANTT)
  const sum = ganttSummary(chart)

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex items-baseline gap-2">
        <h3 className="flex items-center gap-1.5 text-[13px] font-[620]">
          <CalendarClock className="size-3.5 text-muted-foreground" />
          阶段进度甘特
        </h3>
        <span className="text-[11px] text-muted-foreground">
          {chart.startDate} → {chart.endDate} · 全程 {chart.spanDays} 天
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <TonePill tone="blue">总计划 {sum.planDays} 天</TonePill>
          <TonePill tone={sum.late > 0 ? 'red' : 'green'}>{sum.late > 0 ? `${sum.late} 条延期` : '无延期'}</TonePill>
          <TonePill tone="neutral">整体 {sum.progress}%</TonePill>
        </div>
      </div>

      {/* 时间轴刻度 */}
      <div className="relative mt-3 h-[14px] border-b border-border-light">
        {chart.months.map((m) => (
          <span
            key={`${m.label}-${m.left}`}
            className="absolute bottom-[2px] -translate-x-1/2 text-[10px] tabular-nums text-muted-foreground"
            style={{ left: `${m.left}%` }}
          >
            {m.label}
          </span>
        ))}
      </div>

      <div className="mt-2 flex flex-col">
        {chart.bars.map((bar) => (
          <button
            key={bar.row.phaseId}
            type="button"
            onClick={() => onPickPhase(bar.row.phaseId)}
            title={`${bar.seq} ${bar.name} · ${bar.startDate} 至 ${bar.endDate} · 计划 ${bar.row.planDays} 天`}
            className="group flex items-center gap-2 rounded-[7px] px-1 py-[5px] text-left transition-colors hover:bg-secondary/45"
          >
            {/* 阶段名（固定宽，条形左边界因此对齐；只显示主线与 3.x 子阶段的首字缩进） */}
            <span className="flex w-[132px] flex-none items-center gap-1 overflow-hidden">
              <span className="w-[22px] flex-none text-[10.5px] tabular-nums text-muted-foreground">{bar.seq}</span>
              <span
                className={cn(
                  'min-w-0 truncate text-[11.5px]',
                  bar.status === 'doing' ? 'font-[650] text-foreground' : 'text-secondary-foreground',
                  bar.status === 'todo' && 'text-muted-foreground',
                )}
              >
                {bar.name}
              </span>
            </span>

            {/* 轨道 */}
            <span className="relative h-[16px] min-w-0 flex-1 rounded-[3px] bg-secondary/60">
              <span
                className={cn(
                  'absolute top-0 bottom-0 overflow-hidden rounded-[3px] border',
                  bar.status === 'todo'
                    ? 'border-dashed border-border bg-transparent'
                    : bar.drift === 'late'
                      ? 'border-status-red/40 bg-status-red-bg'
                      : 'border-border bg-card',
                )}
                style={{ left: `${bar.left}%`, width: `${Math.max(bar.width, 2.5)}%` }}
              >
                <span
                  className={cn(
                    'absolute inset-y-0 left-0 rounded-[2px]',
                    bar.drift === 'late' ? 'bg-status-red/70' : bar.status === 'done' ? 'bg-foreground' : 'bg-status-blue',
                  )}
                  style={{ width: `${bar.row.progress}%` }}
                />
              </span>
            </span>

            {/* 右侧读数 */}
            <span className="flex w-[150px] flex-none items-center gap-1.5">
              <span className="w-[52px] flex-none text-right text-[10px] tabular-nums text-muted-foreground">
                {bar.row.planDays} 天
              </span>
              <span className="w-[34px] flex-none text-right text-[10px] tabular-nums font-medium">
                {bar.row.progress}%
              </span>
              <TonePill tone={DRIFT_TONE[bar.drift]}>
                {bar.row.actualDays === 0 ? '未开工' : DRIFT_TEXT[bar.drift](bar.driftDays)}
              </TonePill>
              <ChevronRight className="size-3 flex-none text-muted-foreground/50 group-hover:text-foreground" />
            </span>
          </button>
        ))}
      </div>

      <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
        <Legend cls="bg-foreground" label="已完成" />
        <Legend cls="bg-status-blue" label="进行中" />
        <Legend cls="bg-status-red/70" label="延期部分" />
        <Legend cls="border border-dashed border-border bg-transparent" label="未开工" />
        <span className="ml-auto">点任意阶段条可打开阶段抽屉</span>
      </div>
    </Card>
  )
}

function Legend({ cls, label }: { cls: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className={cn('inline-block h-[7px] w-[14px] rounded-[2px]', cls)} />
      {label}
    </span>
  )
}
