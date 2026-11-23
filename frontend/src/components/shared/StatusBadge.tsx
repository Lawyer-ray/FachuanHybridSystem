import type { ReactNode } from 'react'

import { BADGE_TONE_CLS, type Tone } from '@/lib/tone'
import { cn } from '@/lib/utils'

/**
 * 小号内联徽章组件：tone → 颜色的映射表在 lib/tone.ts（领域层也要用同一套档位，
 * 不能让 domain 反向 import components）。这里保留 Tone / BADGE_TONE_CLS 的旧出口，
 * 存量调用方不必跟着改。
 */
export type { Tone }
export { BADGE_TONE_CLS }

/** 小号内联徽章（列表 / 侧栏 / 卡片头部通用） */
export function StatusBadge({
  tone,
  children,
  size = 'sm',
  className,
  title,
}: {
  tone: Tone
  children: ReactNode
  /** sm = 列表行内 11px（默认）；xs = 极紧的行内标签 10px */
  size?: 'xs' | 'sm'
  className?: string
  title?: string
}) {
  return (
    <span
      title={title}
      className={cn(
        'inline-flex flex-none items-center rounded-[4px] border px-1.5 leading-[1.6] font-medium whitespace-nowrap',
        size === 'xs' ? 'text-[10px]' : 'text-[11px]',
        BADGE_TONE_CLS[tone],
        className,
      )}
    >
      {children}
    </span>
  )
}
