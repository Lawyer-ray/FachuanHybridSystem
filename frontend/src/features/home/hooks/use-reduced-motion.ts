/**
 * useReducedMotion - 检测用户是否偏好减少动画
 * @module features/home/hooks/use-reduced-motion
 *
 * 检测 prefers-reduced-motion 媒体查询
 * 在用户偏好减少动画时返回 true
 *
 * Requirements: 9.1, 9.2, 9.3
 */

import { useState, useEffect } from 'react'

/**
 * 检测用户是否偏好减少动画
 *
 * @returns 如果用户偏好减少动画则返回 true
 *
 * @example
 * ```tsx
 * function AnimatedComponent() {
 *   const prefersReducedMotion = useReducedMotion()
 *
 *   return (
 *     <motion.div
 *       animate={prefersReducedMotion ? {} : { y: [0, -10, 0] }}
 *     >
 *       Content
 *     </motion.div>
 *   )
 * }
 * ```
 */
export function useReducedMotion(): boolean {
  const [prefersReducedMotion, setPrefersReducedMotion] = useState(false)

  useEffect(() => {
    // 检查浏览器是否支持 matchMedia
    if (typeof window === 'undefined' || !window.matchMedia) {
      return
    }

    const mediaQuery = window.matchMedia('(prefers-reduced-motion: reduce)')

    // 设置初始值
    setPrefersReducedMotion(mediaQuery.matches)

    // 监听变化
    const handleChange = (event: MediaQueryListEvent) => {
      setPrefersReducedMotion(event.matches)
    }

    // 添加事件监听器
    mediaQuery.addEventListener('change', handleChange)

    // 清理
    return () => {
      mediaQuery.removeEventListener('change', handleChange)
    }
  }, [])

  return prefersReducedMotion
}
