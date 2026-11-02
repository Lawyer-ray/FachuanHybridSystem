/**
 * 关厂清盘工作台共用的小原件（语气标签 / 键值块 / 空态插槽）。
 *
 * 为什么从 `nonlit-workbench.tsx` 搬出来：那个文件的 `Pill` / `Inset` / `SectionHead`
 * 不对外导出，子目录里的抽屉与卡片都要用，复制一份就等于埋两个口径。这里只放
 * **跨卡片共用**的件，单卡的私有排版仍留在各自的组件里。
 */

import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'
import { DetailDrawer } from '@/features/bank-litigation/components/stages/DetailDrawer'

export type Tone = 'neutral' | 'green' | 'red' | 'yellow' | 'blue'

const TONE_CLS: Record<Tone, string> = {
  neutral: 'border-border bg-secondary text-secondary-foreground',
  green: 'border-status-green/40 bg-status-green-bg text-status-green',
  red: 'border-status-red/40 bg-status-red-bg text-status-red',
  yellow: 'border-status-yellow/40 bg-status-yellow-bg text-status-yellow',
  blue: 'border-status-blue/40 bg-status-blue-bg text-status-blue',
}

/** 带语气的状态胶囊 */
export function TonePill({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  return (
    <span
      className={cn(
        'rounded-[6px] border px-2 text-[11px] leading-[1.6] font-semibold whitespace-nowrap',
        TONE_CLS[tone],
      )}
    >
      {children}
    </span>
  )
}

/** 块内嵌层（比卡片更白一层） */
export function Inset({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('rounded-[9px] border border-border-light bg-background px-3 py-2', className)}>{children}</div>
  )
}

/** 节标题 + 右侧动作槽 */
export function BlockHead({ title, hint, action }: { title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="mb-1.5 flex items-baseline gap-2">
      <h4 className="text-[11px] font-[650] tracking-[0.06em] text-muted-foreground/85">{title}</h4>
      {hint ? <span className="text-[10.5px] text-muted-foreground">{hint}</span> : null}
      {action ? <div className="ml-auto flex items-center gap-1.5">{action}</div> : null}
    </div>
  )
}

/** 无内容时的灰字（抽屉四个页签共用） */
export function EmptyHint({ children }: { children: ReactNode }) {
  return <div className="rounded-[9px] border border-dashed border-border-light px-3 py-3 text-[12px] text-muted-foreground">{children}</div>
}

/** 行级小按钮（抽屉动作区的次要动作） */
export function MiniButton({
  onClick,
  title,
  children,
  tone = 'plain',
}: {
  onClick: () => void
  title?: string
  children: ReactNode
  tone?: 'plain' | 'danger'
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      className={cn(
        'inline-flex h-[26px] flex-none items-center gap-1 rounded-[6px] border px-2 text-[11.5px] font-[550] whitespace-nowrap transition-colors',
        tone === 'danger'
          ? 'border-status-red/40 bg-card text-status-red hover:bg-status-red-bg'
          : 'border-border bg-card text-secondary-foreground hover:border-input hover:bg-secondary',
      )}
    >
      {children}
    </button>
  )
}

/**
 * 抽屉外壳：直接复用诉讼线 `DetailDrawer`（右侧滑入 / ESC / 遮罩关闭），
 * 只把「内容宽度」定成 560——阶段抽屉里要放交付物版本表，520 会横向滚。
 */
export function SpecialDrawer({
  open,
  onClose,
  title,
  subtitle,
  badge,
  footer,
  children,
}: {
  open: boolean
  onClose: () => void
  title: string
  subtitle?: string
  badge?: ReactNode
  footer?: ReactNode
  children: ReactNode
}) {
  return (
    <DetailDrawer open={open} onClose={onClose} title={title} subtitle={subtitle} badge={badge} footer={footer} width={560}>
      {children}
    </DetailDrawer>
  )
}
