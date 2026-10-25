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

/** 争议解决详情页 chunk 加载器（/projects/:id；与列表页共享 domain/api，公共代码由构建器自动拆共用块） */
export const preloadDealDetailPage = () => import('./components/deal-detail/DealDetailPage')

/** 争议解决详情页（懒加载组件，消费方需包 Suspense） */
export const DealDetailPageLazy = lazy(() =>
  preloadDealDetailPage().then((m) => ({ default: m.DealDetailPage })),
)

/** 非诉（常法/专项）详情页 chunk 加载器（/projects/:id/nonlit；右栏复用争议解决页，只换左栏） */
export const preloadNonLitDetailPage = () => import('./components/deal-detail/NonLitDetailPage')

/** 非诉详情页（懒加载组件，消费方需包 Suspense） */
export const NonLitDetailPageLazy = lazy(() =>
  preloadNonLitDetailPage().then((m) => ({ default: m.NonLitDetailPage })),
)

/**
 * 项目详情分发：`/projects/:id` 一条 URL，按 `deal.lit` 决定渲染哪一栏。
 *
 * **为什么不再用 `/nonlit` 后缀**：`nonlit` 是 non-litigation 的缩写，属实现
 * 分类而非用户概念——律师只知道「这是个顾问项目」，不会想「这是 nonlit」。
 * 更要紧的是旧实现有隐藏重定向（直达 `/projects/:id` 的非诉委托会被悄悄
 * 转到 `/projects/:id/nonlit`），用户看到 URL 变了却不知道为什么。
 *
 * 分流依据 `lit` 来自合同 `case_type`（civil/criminal/advisor…）的派生，与
 * 左栏内容严格对应：有法院程序 → 案件程序链；无 → 合同文件夹。
 */
export const ProjectDetailPageLazy = lazy(() =>
  import('./components/deal-detail/ProjectDetailPage').then((m) => ({ default: m.ProjectDetailPage })),
)
