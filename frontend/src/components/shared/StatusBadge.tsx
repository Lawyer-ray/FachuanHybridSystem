/* eslint-disable react-refresh/only-export-components */
import type { ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * 状态 → 颜色的单一来源。
 *
 * 之前每个 feature 各自手写 `border-status-X/40 bg-status-X-bg text-status-X`
 * （历史列表 badges.ts、copilot taskBadge、settings 状态卡、合同审查 severity…），
 * 同一语义在不同页面颜色不一致。这里把 tone 收成 6 档，样式表只写一次。
 *
 * 颜色一律取 index.css 里已定义的 `--status-*`（含暗色的 bg 变体），
 * 不硬编码 hex——暗色主题才能随之切换。
 *
 * 文件同时导出 Tone / BADGE_TONE_CLS 与 StatusBadge：调用方常需“只要样式不要组件”
 * （给自定义 <span> 套色），拆文件只会多一层 import；fast-refresh 规则按
 * components/ui/button.tsx 的同样取舍在此文件级关闭（改本文件时整页刷新）。
 */

/** 语义色档位：绿=成功 / 黄=待处理·警告 / 红=失败·高危 / 蓝=进行中·提示 / 紫=特殊 / 灰=中性·已取消 */
export type Tone = 'green' | 'yellow' | 'red' | 'blue' | 'purple' | 'neutral'

/**
 * tone → border / bg / text 三件套。
 * 描边透明度按各色对比度微调（黄最亮需 50，其余 40），沿用历史列表的既有口径。
 */
export const BADGE_TONE_CLS: Record<Tone, string> = {
  green: 'border-status-green/40 bg-status-green-bg text-status-green',
  yellow: 'border-status-yellow/50 bg-status-yellow-bg text-status-yellow',
  red: 'border-status-red/40 bg-status-red-bg text-status-red',
  blue: 'border-status-blue/40 bg-status-blue-bg text-status-blue',
  purple: 'border-status-purple/40 bg-status-purple-bg text-status-purple',
  neutral: 'border-border bg-secondary text-muted-foreground',
}

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
