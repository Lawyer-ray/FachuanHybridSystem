/**
 * useCounterAnimation - 数字计数动画 Hook
 * @module features/home/hooks/use-counter-animation
 *
 * 实现数字从 0 计数到目标值的动画效果
 * 使用 useInView 触发动画
 *
 * Requirements: 2.8, 2.9
 */

import { useEffect, useState, useRef, useCallback } from 'react'
import { useInView } from 'framer-motion'

interface UseCounterAnimationOptions {
  /** 动画持续时间（毫秒），默认 2000 */
  duration?: number
  /** 是否在进入视口时触发，默认 true */
  startOnView?: boolean
  /** 是否只触发一次，默认 true */
  triggerOnce?: boolean
}

interface UseCounterAnimationReturn {
  /** 当前计数值 */
  count: number
  /** 需要附加到元素的 ref */
  ref: React.RefObject<HTMLElement | null>
  /** 动画是否完成 */
  isComplete: boolean
}

/**
 * easeOutExpo 缓动函数
 * 快速开始，缓慢结束
 */
function easeOutExpo(progress: number): number {
  return progress === 1 ? 1 : 1 - Math.pow(2, -10 * progress)
}

/**
 * 数字计数动画 Hook
 *
 * @param target - 目标数值
 * @param options - 配置选项
 * @returns 当前计数值和 ref
 *
 * @example
 * ```tsx
 * function StatsCounter({ value }: { value: number }) {
 *   const { count, ref } = useCounterAnimation(value)
 *   return <span ref={ref}>{count}</span>
 * }
 * ```
 */
export function useCounterAnimation(
  target: number,
  options: UseCounterAnimationOptions = {}
): UseCounterAnimationReturn {
  const { duration = 2000, startOnView = true, triggerOnce = true } = options

  const [count, setCount] = useState(0)
  const [isComplete, setIsComplete] = useState(false)
  const ref = useRef<HTMLElement>(null)
  const hasAnimated = useRef(false)

  // 使用 framer-motion 的 useInView
  const isInView = useInView(ref, {
    once: triggerOnce,
    amount: 0.5, // 元素 50% 可见时触发
  })

  const animate = useCallback(() => {
    const startTime = performance.now()

    const tick = (currentTime: number) => {
      const elapsed = currentTime - startTime
      const progress = Math.min(elapsed / duration, 1)
      const eased = easeOutExpo(progress)
      const currentValue = Math.floor(eased * target)

      setCount(currentValue)

      if (progress < 1) {
        requestAnimationFrame(tick)
      } else {
        // 确保最终值精确等于目标值
        setCount(target)
        setIsComplete(true)
      }
    }

    requestAnimationFrame(tick)
  }, [target, duration])

  useEffect(() => {
    // 如果不需要等待进入视口，直接开始动画
    if (!startOnView) {
      if (!hasAnimated.current) {
        hasAnimated.current = true
        animate()
      }
      return
    }

    // 等待进入视口后开始动画
    if (isInView && !hasAnimated.current) {
      hasAnimated.current = true
      animate()
    }
  }, [isInView, startOnView, animate])

  return { count, ref, isComplete }
}
