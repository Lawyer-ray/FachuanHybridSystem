/**
 * 合同复审工作台 feature 的对外出口。
 * 其它 feature / app 层只应从这里引，不穿透内部目录。
 *
 * 页面组件走 lazy 出口（照 workbench/index.ts 模式）：静态 re-export 会把整域
 * 钉进首屏 chunk。
 */

import { lazy } from 'react'

/** 复审工作台 chunk 加载器：lazy 出口与导航预取共用同一个 import() */
export const preloadReviewWorkbenchPage = () => import('./components/ReviewWorkbenchPage')

/** 合同复审工作台（懒加载组件，消费方需包 Suspense） */
export const ReviewWorkbenchPageLazy = lazy(() =>
  preloadReviewWorkbenchPage().then((m) => ({ default: m.ReviewWorkbenchPage })),
)

export { useRevisions } from './hooks/use-revisions'
export * from './types'
export { ReviewLaunchDrawer } from './components/ReviewLaunchDrawer'
export { DirectEditDialog } from './components/DirectEditDialog'
