import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * 跨境审查子域的小件。
 *
 * 自己带一份带语气的 Pill：`deal-detail/ui.tsx` 的 Pill 是公共件（不带 tone 且禁止修改），
 * 而这一屏要表达「高/中/低风险」「已挂法条/需律师判断」「对方接受/还价/拒绝」这些语气。
 */
export function TonePill({
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
    yellow: 'border-status-yellow/70 bg-status-yellow-bg text-status-yellow',
    blue: 'border-status-blue/40 bg-status-blue-bg text-status-blue',
  } as const
  return (
    <span className={cn('rounded-[6px] border px-2 text-[11px] leading-[1.6] font-semibold whitespace-nowrap', map[tone])}>
      {children}
    </span>
  )
}
