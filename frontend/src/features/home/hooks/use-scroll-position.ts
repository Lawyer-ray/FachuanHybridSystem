/**
 * 滚动位置检测 Hook
 * @module features/home/hooks/use-scroll-position
 *
 * 用于检测页面滚动位置，实现导航栏样式切换
 * Validates: Requirements 1.3
 */

import { useState, useEffect, useCallback } from 'react'
import { SCROLL_THRESHOLD } from '../constants'

export interface ScrollPositionState {
  /** 当前滚动位置 Y 值 */
  scrollY: number
  /** 是否已滚动超过阈值 */
  isScrolled: boolean
}

/**
 * 监听页面滚动位置
 * @param threshold - 滚动阈值，默认 50px
 * @returns 滚动状态对象
 */
export function useScrollPosition(threshold: number = SCROLL_THRESHOLD): ScrollPositionState {
  const [scrollY, setScrollY] = useState(0)
  const [isScrolled, setIsScrolled] = useState(false)

  const handleScroll = useCallback(() => {
    // 使用 requestAnimationFrame 节流，优化性能
    requestAnimationFrame(() => {
      const currentScrollY = window.scrollY
      setScrollY(currentScrollY)
      setIsScrolled(currentScrollY > threshold)
    })
  }, [threshold])

  useEffect(() => {
    // 初始化时检查当前滚动位置
    handleScroll()

    // 使用 passive 事件监听器优化滚动性能
    window.addEventListener('scroll', handleScroll, { passive: true })

    return () => {
      window.removeEventListener('scroll', handleScroll)
    }
  }, [handleScroll])

  return { scrollY, isScrolled }
}
