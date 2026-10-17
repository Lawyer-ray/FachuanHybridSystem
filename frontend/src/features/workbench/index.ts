/**
 * 办案主页 feature 的对外出口。
 * 其它 feature / app 层只应从这里引，不穿透内部目录。
 *
 * 页面组件走 lazy 出口（照 auth/index.ts 模式）：静态 re-export 会把整域
 * 钉进首屏 chunk，dynamic import 拆不出独立 chunk（INEFFECTIVE_DYNAMIC_IMPORT）。
 */

import { lazy } from 'react'

/** 办案主页 chunk 加载器：lazy 出口与导航预取共用同一个 import()，浏览器模块缓存保证只下载一次 */
export const preloadWorkbenchPage = () => import('./components/WorkbenchPage')

/** 办案主页（懒加载组件，消费方需包 Suspense） */
export const WorkbenchPageLazy = lazy(() =>
  preloadWorkbenchPage().then((m) => ({ default: m.WorkbenchPage })),
)
