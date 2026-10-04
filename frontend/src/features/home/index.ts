/**
 * 首页 · 今日工作台 的对外出口。
 * 其它 feature / app 层只应从这里引，不穿透内部目录。
 *
 * 页面组件走 lazy 出口（照 workbench/index.ts 模式）：静态 re-export 会把
 * 整域（含 ToolDock 的法院短信/转换器等弹窗全家桶）钉进首屏 chunk，
 * dynamic import 拆不出独立 chunk（INEFFECTIVE_DYNAMIC_IMPORT）。
 */

import { lazy } from 'react'

/** 首页 · 今日工作台（懒加载组件，消费方需包 Suspense） */
export const HomePageLazy = lazy(() =>
  import('./components/HomePage').then((m) => ({ default: m.HomePage })),
)
