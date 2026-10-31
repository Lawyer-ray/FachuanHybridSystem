/**
 * 案件工作台（bank-litigation）共用 UI 原子件。
 *
 * ═══ 为什么要单独建这一层 ═══
 * 这块业务原先只有一个「左栏 7 分区 + 右栏内容」的裸壳：每个面板各自写
 * `<div className="flex flex-col gap-2.5">`，没有任何卡片、分区标题或数据块，
 * 于是整页看起来就是**一堆灰字贴在白底上**——尤其在 1400px 以上的宽屏，
 * 内容只占左半边，右半边全是空白，像没做完的原型。
 *
 * 抽这四个原子件的理由：
 *   - `WorkCard`     统一卡片气泡感（边框/圆角/内边距），7 个面板共用一份
 *   - `SectionTitle` 统一「标题 + 右侧动作」的行结构，避免每处手写 h3 + flex
 *   - `StatTile`     把「一个数字 + 一句标签」做成块，横向铺满宽屏
 *   - `KeyValueRow`  统一 label/value 的两栏对齐（原先是 dl + 各种手写 grid）
 *
 * 这些只服务本 feature，**不上提到 components/shared**：
 * 别的业务域没有「左栏分区工作台」这种形态，提权会变成幽灵共享。
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
        'rounded-[10px] border border-border bg-card',
        'shadow-[0_1px_2px_rgba(0,0,0,.03)]',
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

/** 数字块：大数字 + 标签，用于横向铺开统计（5/5、缺 2、¥99.8万…） */
export function StatTile({
  label,
  value,
  unit,
  tone = 'neutral',
}: {
  label: string
  value: ReactNode
  unit?: string
  tone?: 'neutral' | 'green' | 'red' | 'yellow' | 'blue'
}) {
  const toneMap = {
    neutral: 'text-foreground',
    green: 'text-status-green',
    red: 'text-status-red',
    yellow: 'text-status-yellow',
    blue: 'text-status-blue',
  } as const
  return (
    <div className="flex flex-col gap-0.5 rounded-[8px] border border-border bg-secondary/25 px-3 py-2">
      <span className="text-[10.5px] text-muted-foreground">{label}</span>
      <span className={cn('flex items-baseline gap-0.5 text-[17px] font-semibold tabular-nums leading-tight', toneMap[tone])}>
        {value}
        {unit ? <span className="text-[11px] font-normal text-muted-foreground">{unit}</span> : null}
      </span>
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
    <div className={cn('grid grid-cols-[92px_minmax(0,1fr)] items-center gap-x-3 py-[5px]', className)}>
      <dt className="text-[11.5px] text-muted-foreground">{label}</dt>
      <dd className="min-w-0 text-[12.5px]">{children}</dd>
    </div>
  )
}
