/**
 * ReducedMotionContext - 动画降级上下文
 * @module features/home/contexts/ReducedMotionContext
 *
 * 提供全局的动画降级状态
 * Requirements: 9.1, 9.2, 9.3
 */

import { createContext, useContext, type ReactNode } from 'react'
import { useReducedMotion } from '../hooks/use-reduced-motion'

// ============================================================================
// Context 定义
// ============================================================================

interface ReducedMotionContextValue {
  /** 用户是否偏好减少动画 */
  prefersReducedMotion: boolean
}

const ReducedMotionContext = createContext<ReducedMotionContextValue>({
  prefersReducedMotion: false,
})

// ============================================================================
// Provider 组件
// ============================================================================

interface ReducedMotionProviderProps {
  children: ReactNode
}

/**
 * 动画降级 Provider
 *
 * 包裹应用以提供全局的动画降级状态
 *
 * @example
 * ```tsx
 * <ReducedMotionProvider>
 *   <App />
 * </ReducedMotionProvider>
 * ```
 */
export function ReducedMotionProvider({ children }: ReducedMotionProviderProps) {
  const prefersReducedMotion = useReducedMotion()

  return (
    <ReducedMotionContext.Provider value={{ prefersReducedMotion }}>
      {children}
    </ReducedMotionContext.Provider>
  )
}

// ============================================================================
// Hook
// ============================================================================

/**
 * 使用动画降级上下文
 *
 * @returns 动画降级状态
 *
 * @example
 * ```tsx
 * function AnimatedComponent() {
 *   const { prefersReducedMotion } = useReducedMotionContext()
 *
 *   return (
 *     <motion.div
 *       animate={prefersReducedMotion ? {} : { scale: [1, 1.1, 1] }}
 *     >
 *       Content
 *     </motion.div>
 *   )
 * }
 * ```
 */
export function useReducedMotionContext(): ReducedMotionContextValue {
  return useContext(ReducedMotionContext)
}
