import type { ReactNode } from 'react'
import { Loader2 } from 'lucide-react'

import { errMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

/**
 * 加载 / 空 / 错 三态的单一来源。
 *
 * 此前 repo 里散着 35 处手写的同一套块（居中灰字 + 可选 Loader2 spin / 红字 +
 * 「重试」下划线按钮），视觉口径已经漂移（有的 px-4 py-8、有的 py-10、有的
 * 带边框红块）。共用一处后，调用点只传文案与回调，样式统一在这里改。
 *
 * 三者都是纯展示：取数、重试动作由调用方给（本库不碰 react-query）。
 */

/** 加载中：居中灰字 + Loader2 转圈。text 默认「加载中…」 */
export function LoadingBlock({
  text = '加载中…',
  size = 'md',
  className,
}: {
  text?: string
  /** 图标尺寸档：sm 用于弹窗内部（12px 文字），md 用于页面级块 */
  size?: 'sm' | 'md'
  className?: string
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={cn(
        'flex items-center justify-center gap-2 py-8 text-center text-muted-foreground',
        size === 'sm' ? 'text-[12px]' : 'text-sm',
        className,
      )}
    >
      <Loader2 className={cn('animate-spin', size === 'sm' ? 'size-3.5' : 'size-4')} />
      {text}
    </div>
  )
}

/**
 * 空状态：居中灰字，可选 lucide 图标与动作槽（按钮 / 链接）。
 * action 与 children 分开是为了让「说明文案 + 一个补救动作」成为固定结构。
 */
export function EmptyBlock({
  children,
  icon,
  action,
  className,
}: {
  children: ReactNode
  /** 顶部的 lucide 图标元素（如 <Inbox className="size-6" />），不给则不占位 */
  icon?: ReactNode
  /** 底部动作槽（「上传材料」按钮之类），不给则不渲染 */
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'flex flex-col items-center justify-center gap-2 px-4 py-8 text-center text-[12px] text-muted-foreground',
        className,
      )}
    >
      {icon ? <div className="text-muted-foreground/60">{icon}</div> : null}
      <div>{children}</div>
      {action ? <div className="pt-1">{action}</div> : null}
    </div>
  )
}

/**
 * 错误状态：destructive 色块 + 可选「重试」。
 *
 * error 原样交给 errMessage 抽取文案（ky HTTPError / TimeoutError / 普通 Error
 * 各自取到可读中文），取不到才回 fallback——否则列表查询失败会被渲染成空列表，
 * 用户把服务端故障读成「没有数据」。
 */
export function ErrorBlock({
  error,
  onRetry,
  fallback = '加载失败，请重试',
  retryText = '重新加载',
  className,
}: {
  error: unknown
  onRetry?: () => void
  fallback?: string
  retryText?: string
  className?: string
}) {
  return (
    <div
      role="alert"
      className={cn(
        'rounded-[10px] border border-destructive/30 bg-destructive/5 px-4 py-6 text-center text-[12px] text-destructive',
        className,
      )}
    >
      {errMessage(error, fallback)}
      {onRetry ? (
        <button
          type="button"
          className="ml-2 cursor-pointer underline underline-offset-3"
          onClick={onRetry}
        >
          {retryText}
        </button>
      ) : null}
    </div>
  )
}
