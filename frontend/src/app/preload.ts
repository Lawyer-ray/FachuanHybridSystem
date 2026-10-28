import { lazy } from 'react'

import { HomePageLazy, preloadHomePage } from '@/features/home'
import { preloadWorkbenchPage, ProjectDetailPageLazy, WorkbenchPageLazy } from '@/features/workbench'
import { ReviewWorkbenchPageLazy } from '@/features/contract-review'
import { SettingsPageLazy } from '@/features/settings'

import { ROUTES } from './paths'

/**
 * 路由级懒加载与预取：页面 chunk 的声明（lazy）+ 导航入口到加载器的映射。
 *
 * 从 App.tsx 抽出来的原因不只是行数：lazy() 声明与 ROUTE_PRELOADERS 必须
 * 指向**同一个 import()**，否则悬停预取与真正导航会各拉一份、或者预取了
 * 一个没人用的 chunk。放在一个文件里，改漏看得见。
 */

// 材料预处理整域懒加载：它静态引入 pdfjs-dist（~1MB 级），不拆出去的话
// 登录页/首页的首屏包也要背上它。列表页与详情页共用同一 chunk，切换零成本。
const preloadDeskPage = () => import('@/features/material-prep')
export const DeskPageLazy = lazy(() => preloadDeskPage().then((m) => ({ default: m.DeskPage })))

// 收件箱页：独立轻量 chunk（只依赖 react-query + ky，不背 pdfjs）。
// 与材料预处理分开拆，是因为从收件箱点进材料包时才需要 pdfjs。
const preloadInboxPage = () => import('@/features/inbox')
export const InboxPageLazy = lazy(() => preloadInboxPage().then((m) => ({ default: m.InboxPage })))

// AI 助手面板懒加载：只在首次展开时加载 copilot 域；挂壳层、跨路由常驻，
// 收起面板不卸载状态（流式收发在 store，见 features/copilot）。
export const CopilotPanelLazy = lazy(() =>
  import('@/features/copilot').then((m) => ({ default: m.CopilotPanel })),
)
export const PanelBackdropLazy = lazy(() =>
  import('@/features/copilot').then((m) => ({ default: m.PanelBackdrop })),
)

// 客户上传单页（公开）：律师生成 /u/{token} 链接一对一发给客户，免登录上传。
// 独立轻量 chunk（不带 pdfjs 等重依赖），放 RequireAuth 之外与 /login 平级。
export const ClientUploadPageLazy = lazy(() =>
  import('@/features/client-upload').then((m) => ({ default: m.ClientUploadPage })),
)

/**
 * 导航入口 → 页面 chunk 加载器。悬停预取（AppNavbar onPrefetch）与登录后的
 * 空闲预载共用；import() 幂等，重复调用只命中浏览器模块缓存。
 * 账号绑定页走用户菜单、访问频率低，不在预载之列。
 */
const ROUTE_PRELOADERS: Record<string, () => Promise<unknown>> = {
  [ROUTES.home]: preloadHomePage,
  [ROUTES.inbox]: preloadInboxPage,
  [ROUTES.materialPrep]: preloadDeskPage,
  [ROUTES.projects]: preloadWorkbenchPage,
}

// 其余页面沿用各 feature 的 lazy 出口（chunk 加载器与预取共用同一个 import()）。
// 集中在这里 re-export，router 只需从本文件取页面组件。
export {
  HomePageLazy,
  ProjectDetailPageLazy,
  ReviewWorkbenchPageLazy,
  SettingsPageLazy,
  WorkbenchPageLazy,
}

export function preloadRoute(to: string) {
  // 预取失败不用管：真正导航时 lazy 会再拉一次，失败由 ErrorBoundary 兜底
  void ROUTE_PRELOADERS[to]?.().catch(() => {})
}

/** 登录后空闲预载全部主入口（壳层挂载时调一次） */
export function preloadAllRoutes() {
  for (const to of Object.keys(ROUTE_PRELOADERS)) preloadRoute(to)
}

/** 浏览器空闲时执行（Safari 无 requestIdleCallback，退化为短延时） */
export function whenIdle(cb: () => void): () => void {
  if (typeof window.requestIdleCallback === 'function') {
    const id = window.requestIdleCallback(cb, { timeout: 3000 })
    return () => window.cancelIdleCallback(id)
  }
  const id = window.setTimeout(cb, 1500)
  return () => window.clearTimeout(id)
}
