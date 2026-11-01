/**
 * 案件工作台（bank-litigation）共用 UI 原子件。
 *
 * ═══ 为什么要单独建这一层 ═══
 * 这块业务原先只有一个「左栏 7 分区 + 右栏内容」的裸壳：每个面板各自写
 * `<div className="flex flex-col gap-2.5">`，没有任何卡片、分区标题或数据块，
 * 于是整页看起来就是**一堆灰字贴在白底上**。
 *
 * 抽这一层的第二版（2026-11-01）针对「内容只占上半屏、下面全白」的问题：
 * 光有卡片边界还不够，**页面必须撑满视口、左右必须分栏**，否则 1080p 屏上
 * 内容到 419px 就结束，剩下 660px 空白——那才是「不美观」的真实来源。
 */

import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/** 统一的白色卡片容器 */
export function WorkCard({
  children,
  className,
  padded = true,
}: {
  children: ReactNode
  className?: string
  /** 关掉内边距（表格类内容自己贴边） */
  padded?: boolean
}) {
  return (
    <section
      className={cn(
        'rounded-[12px] border border-border bg-card',
        'shadow-[0_1px_2px_rgba(0,0,0,.03),0_8px_24px_-16px_rgba(0,0,0,.10)]',
        padded && 'px-4 py-3.5',
        className,
      )}
    >
      {children}
    </section>
  )
}

/** 分区标题：左侧标题 + 可选副标题，右侧动作区 */
export function SectionTitle({
  title,
  hint,
  action,
  className,
}: {
  title: string
  hint?: string
  action?: ReactNode
  className?: string
}) {
  return (
    <div className={cn('flex items-baseline gap-2', className)}>
      <h3 className="text-[12.5px] font-semibold text-foreground">{title}</h3>
      {hint ? <span className="text-[11px] text-muted-foreground">{hint}</span> : null}
      {action ? <div className="ml-auto flex items-center gap-1.5">{action}</div> : null}
    </div>
  )
}

/** 数字块：大数字 + 标签，用于横向铺开统（5/5、缺 2、¥99.8万…） */
export function StatTile({
  label,
  value,
  unit,
  tone = 'neutral',
  hint,
}: {
  label: string
  value: ReactNode
  unit?: string
  tone?: 'neutral' | 'green' | 'red' | 'yellow' | 'blue'
  hint?: string
}) {
  const toneMap = {
    neutral: 'text-foreground',
    green: 'text-status-green',
    red: 'text-status-red',
    yellow: 'text-status-yellow',
    blue: 'text-status-blue',
  } as const
  return (
    <div className="flex flex-col gap-1 rounded-[10px] border border-border bg-secondary/20 px-3.5 py-3">
      <span className="text-[10.5px] font-medium tracking-[.02em] text-muted-foreground">{label}</span>
      <span
        className={cn(
          'flex items-baseline gap-0.5 text-[20px] font-semibold tabular-nums leading-none',
          toneMap[tone],
        )}
      >
        {value}
        {unit ? <span className="text-[11px] font-normal text-muted-foreground">{unit}</span> : null}
      </span>
      {hint ? <span className="truncate text-[10px] text-muted-foreground">{hint}</span> : null}
    </div>
  )
}

/** 两栏键值行：label 固定宽，value 可截断 */
export function KeyValueRow({
  label,
  children,
  className,
}: {
  label: string
  children: ReactNode
  className?: string
}) {
  return (
    <div className={cn('grid grid-cols-[92px_minmax(0,1fr)] items-center gap-x-3 py-[7px]', className)}>
      <dt className="text-[11.5px] text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-[12.5px]">{children}</dd>
    </div>
  )
}

/** 竖排进度关节：用在右栏「当前走到哪」 */
export function StepItem({
  index,
  title,
  desc,
  state,
}: {
  index: number
  title: string
  desc?: string
  state: 'done' | 'current' | 'todo' | 'blocked'
}) {
  const dot =
    state === 'done'
      ? 'bg-status-green text-white'
      : state === 'current'
        ? 'bg-foreground text-background ring-4 ring-foreground/10'
        : state === 'blocked'
          ? 'bg-status-red text-white'
          : 'bg-secondary text-muted-foreground'
  return (
    <div className="flex gap-2.5">
      <div className="flex flex-none flex-col items-center">
        <span
          className={cn(
            'grid size-[18px] place-items-center rounded-full text-[10px] font-semibold tabular-nums',
            dot,
          )}
        >
          {state === 'done' ? '✓' : index}
        </span>
        <span className="mt-1 w-px flex-1 bg-border last:hidden" />
      </div>
      <div className="min-w-0 pb-3.5">
        <div
          className={cn(
            'text-[12px] leading-tight',
            state === 'todo' ? 'text-muted-foreground' : 'font-medium text-foreground',
          )}
        >
          {title}
        </div>
        {desc ? <div className="mt-0.5 text-[10.5px] leading-tight text-muted-foreground">{desc}</div> : null}
      </div>
    </div>
  )
}
