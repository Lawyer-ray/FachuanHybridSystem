import { useEffect, useReducer } from 'react'

import { useMediaQuery } from '@/hooks/use-media'

/**
 * 页面「净宽」：`100vw − AI 助手宽度`（54 号原型与正式前端共用的口径）。
 *
 * **为什么不能用量出来的宽度**：AI 助手是 `position: fixed` 的抽屉，不占文档流，
 * 容器查询与新 ResizeObserver 都测不到它；而详情页在宽屏下助手恒并排让位，主区
 * 被压掉数百像素。所以净宽只能自己算：视口宽 − 并排时的助手宽度
 * （`--copilot-w-app` 由 CopilotPanel 的 resize hook 同步在 `<html>` 上，
 * 未并排时为 0）。
 *
 * 实测：滚动条存在时 `100vw` 仍等于 `innerWidth`（不扣滚动条槽），与原型判定一致。
 *
 * 重算时机：窗口 resize 与助手拖动（助手根元素广播 `copilot-width-change`）。
 * 用冒泡而非常驻 ResizeObserver——它只决定「文档在右 / 文档通栏」这一个二选一。
 */
export function useNetWidth(): number {
  const [, bump] = useReducer((n: number) => n + 1, 0)
  useEffect(() => {
    const onResize = () => bump()
    window.addEventListener('resize', onResize)
    document.documentElement.addEventListener('copilot-width-change', onResize)
    return () => {
      window.removeEventListener('resize', onResize)
      document.documentElement.removeEventListener('copilot-width-change', onResize)
    }
  }, [])
  if (typeof window === 'undefined') return Number.POSITIVE_INFINITY
  const raw = getComputedStyle(document.documentElement).getPropertyValue('--copilot-w-app').trim()
  const helper = raw.endsWith('px') ? Number.parseFloat(raw) || 0 : 0
  return window.innerWidth - helper
}

/** 宽屏判定（≥1280）：详情页在此宽度下助手恒并排让位 */
export function useDockedViewport(): boolean {
  return useMediaQuery('(min-width: 1280px)')
}
