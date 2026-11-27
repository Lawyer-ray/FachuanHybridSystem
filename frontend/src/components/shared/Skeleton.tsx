import { useEffect, useState, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

/**
 * 骨架屏原语（两个消费者：项目主页列表 / 材料预处理收件箱）。
 *
 * ## 为什么不直接抄 shadcn 的 skeleton
 *
 * shadcn 那一版只有十来行——一个 `animate-pulse rounded-md bg-accent` 的灰块。
 * 它缺的正是三条生产细节：
 * 1. **a11y**：一堆灰块对读屏是空内容，页面上什么都不播报；
 * 2. **延迟**：请求 80ms 回来时骨架只闪一帧，比不显示骨架更晃眼；
 * 3. **reduced-motion**：系统开了「减少动态效果」还照样脉冲。
 * 照抄等于把这三条丢掉，所以这里把灰块（`Skeleton`）和
 * 播报 + 延迟壳（`SkeletonStatus`）拆成两层，各自可单独复用。
 *
 * ## delayMs 的口径
 *
 * 取 GitHub Primer 的 `SkeletonBox`：那边 delay 是
 * `'short' = 300ms / 'long' = 1000ms / number` 的 props，默认档就是 300ms。
 * 含义是「短于 300ms 就回来的请求，用户根本不该看见骨架」——这里沿用同口径，
 * 用 `SkeletonStatus` 的 `delayMs` 表达；不引 `react-loading-skeleton` 这类包，
 * 它们同样只管灰块、不管播报与延迟。
 *
 * ## sr-only 文案是必需的
 *
 * 原来的加载态是 `AsyncState` 的 `LoadingBlock`，它本来就有 `role="status"` +
 * `aria-live="polite"`，读屏会播报「正在加载项目数据…」。换成骨架不能倒退成
 * 「转圈还在、播报没了」：灰块本身读不出来，所以文案用 `sr-only` 挂进同一个
 * 播报区，视觉上不占位、读屏照样念。
 *
 * 纯展示：取数、超时、重试都由调用方负责（本库不碰 react-query）。
 */

/** 单个灰块。纯装饰：`aria-hidden` + `data-slot`，不进无障碍树也不被读屏念到。 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      data-slot="skeleton"
      className={cn('animate-pulse rounded-md bg-accent motion-reduce:animate-none', className)}
    />
  )
}

/**
 * 骨架的「播报 + 延迟」壳。
 *
 * `delayMs` 内返回 null（防「闪一帧」），到点才挂出 `role="status"` 的播报区；
 * 文案走 `sr-only`，骨架本身走 children。卸载时 clearTimeout——定时器不许
 * 回头对已卸载的组件 setState（会报 act 警告，也会在快速切页时留下野更新）。
 */
export function SkeletonStatus({
  text,
  delayMs = 300,
  className,
  children,
}: {
  /** 读屏播报文案（如「正在加载项目数据…」），视觉上不占位 */
  text: string
  /** 延迟窗口：短于它的请求不显示骨架。默认 300ms，与 Primer 的 'short' 同档 */
  delayMs?: number
  className?: string
  children: ReactNode
}) {
  // delayMs<=0 = 立即显示（首帧就挂出来，不走定时器，用于测试与「确定会慢」的调用点）
  const [visible, setVisible] = useState(delayMs <= 0)

  useEffect(() => {
    if (delayMs <= 0) return
    const timer = window.setTimeout(() => setVisible(true), delayMs)
    return () => window.clearTimeout(timer)
  }, [delayMs])

  if (!visible) return null

  return (
    <div role="status" aria-live="polite" aria-busy="true" className={className}>
      <span className="sr-only">{text}</span>
      {children}
    </div>
  )
}
