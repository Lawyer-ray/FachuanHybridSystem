/**
 * 案件工作台（bank-litigation）共用 UI 原子件。
 *
 * ═══ 为什么单独建层，以及为什么 v3 要对齐 workbench ═══
 * 这块业务最初只有「左栏 7 分区 + 右栏裸内容」，没有卡片边界（v1）；
 * 加卡片后发现页面只占上半屏（v2）；v3 统一到**项目详情页
 * （workbench/deal-detail/ui.tsx）的视觉语言**：
 *
 * 同一个案子既可能从 `/projects/:id` 进（项目详情），也可能从
 * `/bank-litigation/:id` 进（立案工作台）。两条路径如果长两个样，
 * 律师会怀疑是两个系统。所以这里刻意复刻 workbench 的口径：
 *
 *   Card        圆角 12px + border-border + shadow-sm（与 deal-detail 的 Card 完全一致）
 *   ActionButton 主/次两档，27px / 31px 两尺寸（与 deal-detail 的 ActionButton 一致）
 *   Pill/Chip   11px 字、px-2、rounded-6px，等宽数字
 *   页面容器     mx-auto + 30px 边距 + 自 1400px 起的阶梯式最大宽度
 *
 * workbench 的这四个件是 `components/deal-detail/ui.tsx` 的域内实现（不满 2 个
 * feature 使用，按规范不能提权到 components/shared）。这里做**同口径的平行实现**
 * 而不是 import 它——跨 feature import 是硬红线，且立案工作台未来可能独立演进。
 * 视觉口径的一致性靠注释与常量对齐来守，不靠共享代码。
 */

import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/** 统一卡片：与 deal-detail 的 `Card` 完全同口径 */
export function WorkCard({
  children,
  className,
  padded = true,
  id,
}: {
  children: ReactNode
  className?: string
  /** 关掉内边距（表格类内容自己贴边） */
  padded?: boolean
  id?: string
}) {
  return (
    <section
      id={id}
      className={cn('rounded-[12px] border border-border bg-card shadow-sm', padded && 'px-5 py-4', className)}
    >
      {children}
    </section>
  )
}

/** 分区标题：与 deal-detail 的节标题层级对齐（13px 半粗 + 11px 弱化副标） */
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
      <h3 className="text-[13px] font-[620] text-foreground">{title}</h3>
      {hint ? <span className="text-[11px] text-muted-foreground">{hint}</span> : null}
      {action ? <div className="ml-auto flex items-center gap-1.5">{action}</div> : null}
    </div>
  )
}

/**
 * 主/次动作按钮：与 deal-detail 的 `ActionButton` 同口径
 * （27px sm / 31px 默认；dark 为主动作）
 */
export function ActionButton({
  dark,
  sm,
  title,
  onClick,
  disabled,
  children,
}: {
  dark?: boolean
  sm?: boolean
  title?: string
  onClick?: () => void
  disabled?: boolean
  children: ReactNode
}) {
  const size = sm ? 'h-[27px] px-2.5 text-[11.5px] ' : 'h-[31px] px-[13px] text-[12.5px] '
  const tone = dark
    ? 'border-foreground bg-foreground font-semibold text-background hover:opacity-85'
    : 'border-border bg-card font-[550] text-secondary-foreground hover:border-input hover:bg-secondary'
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-[8px] border transition-colors disabled:cursor-not-allowed disabled:opacity-50',
        size,
        tone,
      )}
    >
      {children}
    </button>
  )
}

/** 状态胶囊：与 deal-detail 的 `Pill` 同口径 */
export function Pill({
  children,
  tone = 'neutral',
}: {
  children: ReactNode
  tone?: 'neutral' | 'green' | 'red' | 'yellow' | 'blue'
}) {
  const map = {
    neutral: 'border-border bg-secondary text-secondary-foreground',
    green: 'border-status-green/40 bg-status-green-bg text-status-green',
    red: 'border-status-red/40 bg-status-red-bg text-status-red',
    yellow: 'border-status-yellow/40 bg-status-yellow-bg text-status-yellow',
    blue: 'border-status-blue/40 bg-status-blue-bg text-status-blue',
  } as const
  return (
    <span
      className={cn(
        'rounded-[6px] border px-2 text-[11px] leading-[1.6] font-semibold whitespace-nowrap',
        map[tone],
      )}
    >
      {children}
    </span>
  )
}

/** 等宽数字 chip：与 deal-detail 的 `Chip` 同口径 */
export function Chip({ children }: { children: ReactNode }) {
  return (
    <span className="rounded-[6px] border border-border-light bg-background px-2 text-[11.5px] leading-[1.7] font-semibold tabular-nums text-secondary-foreground">
      {children}
    </span>
  )
}

/**
 * 数字块：大数字 + 标签。
 *
 * 与 workbench 的 `.tile` 统计格对齐：数值 20px 半粗、标签 10.5px 弱化。
 * 这里不直接复用 Pill，因为统计块需要**强调数值**（5/5、缺 2），
 * 而 Pill 是等权重的状态标签。
 */
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

/** 两栏键值行 */
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

/** 竖排进度关节 */
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
