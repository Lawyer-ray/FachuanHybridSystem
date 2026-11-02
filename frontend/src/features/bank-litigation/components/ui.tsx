/**
 * 案件工作台（bank-litigation）共用 UI 原子件。
 *
 * ═══ 口径来源：`workbench/deal-detail/ui.tsx` ═══
 * 同一个案子既可能从 `/projects/:id` 进（项目详情），也可能从
 * `/bank-litigation/:id` 进（立案工作台）。两条路径如果长两个样，
 * 律师会怀疑是两个系统。这里按 deal-detail 的**四层视觉手法**复刻：
 *
 *   ① 外卡   rounded-12px + border-border + bg-card + shadow-sm
 *   ② 内嵌块 bg-background（比卡片白底「更白」）+ border-border-light
 *           —— 用于把一组只读值包成一块（如案卡里的「法院/收案/案由」行）
 *   ③ 统计格 bg-secondary/30（zinc-100 半透明）+ divide-x divide-border-light
 *           —— 用于「已收/已开票/未收」这种并排数字
 *   ④ 分隔线 border-border-light（#f4f4f5，比 border-border #e4e4e7 更淡）
 *           —— 卡片内部不分多张卡，用一根淡线分段
 *
 * workbench 的这四个件是 deal-detail 的域内实现（不满 2 个 feature 使用，
 * 按规范不能提权到 components/shared）。这里做**同口径的平行实现**，
 * 视觉一致性靠注释与常量对齐来守（具体值都写在下面）。
 */

import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/** ① 外卡：与 deal-detail 的 `Card` 完全同口径 */
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

/**
 * ② 内嵌块：比卡片白底更「白」的一块只读值区域。
 *
 * 为什么需要它：一张卡里全是同样底色 + 同样字号，读者分不出「这是标题」
 * 还是「这是一组数据」。给一组键值对铺 `bg-background` + 淡边框，
 * 它就从平面里浮出来了 —— deal-detail 的案卡就是这么处理法院/收案/案由那三行的。
 */
export function InsetBlock({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        'rounded-[9px] border border-border-light bg-background px-3 py-2',
        className,
      )}
    >
      {children}
    </div>
  )
}

/**
 * ③ 统计格：并排数字块（已收/已开票/未收 那种）。
 *
 * 整块铺 `bg-secondary/30`，中间用 `divide-x + border-light` 分隔，
 * 外框 `border-light` + `rounded-10px`。比三个独立小卡轻，但比纯文字重得多。
 */
export function StatStrip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={cn(
        'grid divide-x divide-border-light overflow-hidden rounded-[10px] border border-border-light bg-secondary/30',
        className,
      )}
    >
      {children}
    </div>
  )
}

/** 统计格单元（配合 StatStrip 使用） */
export function StatCell({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: ReactNode
  tone?: 'neutral' | 'green' | 'red' | 'yellow' | 'blue'
}) {
  const map = {
    neutral: 'text-foreground',
    green: 'text-status-green',
    red: 'text-status-red',
    yellow: 'text-status-yellow',
    blue: 'text-status-blue',
  } as const
  return (
    <div className="px-3 py-2 text-center">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={cn('mt-0.5 text-[14px] font-[620] tabular-nums', map[tone])}>{value}</div>
    </div>
  )
}

/**
 * ④ 卡内分段：一根淡线把卡片切成几段，不另开卡。
 *
 * deal-detail 的右栏就是这么做的（`RailSection`）：整栏一张卡，
 * 每个语义区块用 `border-t border-border-light` 隔开。
 */
export function RailSection({
  title,
  action,
  children,
  className,
}: {
  title?: string
  action?: ReactNode
  children: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'border-t border-border-light px-[18px] pt-3.5 pb-[15px] first:border-t-0 first:pt-[15px]',
        className,
      )}
    >
      {title ? (
        <div className="mb-[9px] flex items-center gap-2">
          <h4 className="text-[11px] font-[650] tracking-[0.07em] text-muted-foreground/80">{title}</h4>
          {action ? <span className="ml-auto">{action}</span> : null}
        </div>
      ) : null}
      {children}
    </div>
  )
}

/** 分区标题：与 deal-detail 的节标题层级对齐 */
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

/** 主/次动作按钮：与 deal-detail 的 `ActionButton` 同口径（27px sm / 31px 默认） */
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

/** 数字块：大数字 + 标签 */
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
