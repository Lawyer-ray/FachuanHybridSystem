/**
 * 设置 feature 的对外出口。
 *
 * 设置页仅 /settings 单路由使用，走 lazy 出口（理由同 features/auth：静态
 * re-export 会把整域钉进首屏 chunk）。
 */

import { lazy } from 'react'

/** 设置页（懒加载组件，消费方需包 Suspense） */
export const SettingsPageLazy = lazy(() =>
  import('./components/SettingsPage').then((m) => ({ default: m.SettingsPage })),
)
