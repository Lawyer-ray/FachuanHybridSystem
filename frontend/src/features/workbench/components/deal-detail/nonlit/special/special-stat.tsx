/**
 * 非诉工作台汇总条（标题行 + 一格一数的统计条）。
 *
 * 三个工作台（专项 / 跨境审查 / 常年顾问）的顶部汇总都是同一套排版，
 * 原先这三件私有小件长在 `nonlit-workbench.tsx` 里、不对外导出，拆分时若各自
 * 复制一份就等于埋三个口径。放在 special/ 下、与 special-bits 同层，只因为
 * 它最早是从专项工作台那一屏抽出来的；它并不依赖专项的任何领域数据。
 *
 * 与 `special-bits.tsx` 的 `BlockHead` 的区别：BlockHead 是**卡内小节**的标题
 * （小号灰字 h4），SectionHead 是**整卡**标题（13px h3 + 右侧动作槽），不要互换。
 */

import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/** 整卡标题 + 可选副标题 + 右侧动作槽 */
export function SectionHead({
  title,
  hint,
  action,
}: {
  title: string
  hint?: string
  action?: ReactNode
}) {
  return (
    <div className="flex items-baseline gap-2">
      <h3 className="text-[13px] font-[620]">{title}</h3>
      {hint ? <span className="text-[11px] text-muted-foreground">{hint}</span> : null}
      {action ? <div className="ml-auto flex items-center gap-1.5">{action}</div> : null}
    </div>
  )
}

/** 分格统计条（格子由调用方用 grid-cols-* 定；这里只管边框与底色的收口） */
export function StatStrip({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('grid divide-x divide-border-light overflow-hidden rounded-[10px] border border-border-light bg-secondary/30', className)}>
      {children}
    </div>
  )
}

/** 单格：小标签 + 大数字，数值可带语气色 */
export function StatCell({ label, value, tone }: { label: string; value: ReactNode; tone?: 'green' | 'red' | 'yellow' | 'blue' }) {
  const map = {
    green: 'text-status-green',
    red: 'text-status-red',
    yellow: 'text-status-yellow',
    blue: 'text-status-blue',
  } as const
  return (
    <div className="px-3 py-2 text-center">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={cn('mt-0.5 text-[14px] font-[620] tabular-nums', tone ? map[tone] : 'text-foreground')}>{value}</div>
    </div>
  )
}
