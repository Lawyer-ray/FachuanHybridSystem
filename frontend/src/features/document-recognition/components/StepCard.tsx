import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/** 确认清单的分区卡片：步骤徽章（可选）+ 标题 + 右侧 trailing + 内容。 */
export function StepCard({
  step,
  title,
  trailing,
  muted = false,
  children,
}: {
  step?: number
  title: string
  trailing?: ReactNode
  muted?: boolean
  children: ReactNode
}) {
  return (
    <section className="animate-in fade-in slide-in-from-bottom-1 flex flex-col gap-2.5 rounded-[12px] border border-border bg-card px-3.5 py-3 duration-300">
      <div className="flex items-center gap-2">
        {step != null && (
          <span
            className={cn(
              'flex h-[18px] w-[18px] flex-none items-center justify-center rounded-full text-[10px] font-semibold',
              muted ? 'border border-border bg-secondary text-muted-foreground' : 'bg-foreground text-background',
            )}
          >
            {step}
          </span>
        )}
        <span className={cn('text-[13px] font-semibold', muted && 'text-muted-foreground')}>{title}</span>
        {trailing && <span className="ml-auto">{trailing}</span>}
      </div>
      {children}
    </section>
  )
}
