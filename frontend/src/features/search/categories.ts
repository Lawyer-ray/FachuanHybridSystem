import { FolderKanban, Landmark, Mail, Paperclip, Users } from 'lucide-react'

import { materialPrepDetail } from '@/app/paths'

import { projectRoute } from './domain'
import type { CategoryKey, Hit } from './types'

/**
 * 全局检索的类别注册表与面板常量。
 *
 * 从 GlobalSearch.tsx 抽出来：这张表是**数据**（后端有哪些类别、点了去哪），
 * 与面板的开关/焦点/防抖状态机无关。表里的注释（为什么不硬链到没建的页）
 * 也要紧挨着表，而不是夹在组件的 JSX 之间。
 */

/** 一个类别的展示形态：展示名 + 图标 + 点击后的去处 */
export interface CategoryMeta {
  label: string
  icon: typeof Users
  /**
   * 命中 → 站内路径。返回 undefined 表示该类还没有详情页：点选时由调用方
   * 弹提示，而不是硬链到不存在的页——那会命中 App.tsx 的通配重定向、静默
   * 跳回首页，比明确说「还没做」更糟。
   */
  to?: (hit: Hit) => string | undefined
}

/**
 * 各类别 → 展示名 / 图标 / 点击后的去处。
 *
 * projects（项目 = 委托合同，案件挂在合同下）：合同与案件融合展示，
 * 跳转一律走 domain.projectRoute（单条 `/projects/:id`，诉讼/非诉由详情页
 * 内部按 lit 选左栏；案件带 #case-<id> 锚点滚到该案）。
 *
 * 注：不要在这里按诉讼/非诉拼不同 URL——`/projects/:id/nonlit` 已不存在，
 * 拼出来会落到 App.tsx 的 `*` 通配重定向、静默跳回首页。
 *
 * clients 对外叫「当事人」：后端 Client 表装的是所有当事人（我方 + 对方），
 * 叫「客户」会让人以为只有我方委托人。
 */
export const CATEGORIES: Record<CategoryKey, CategoryMeta> = {
  projects: { label: '项目', icon: FolderKanban, to: (h) => projectRoute(h) },
  clients: { label: '当事人', icon: Users },
  inbox: { label: '收件箱', icon: Mail, to: (h) => materialPrepDetail(h.id) },
  court_sms: { label: '法院短信', icon: Landmark },
  contacts: { label: '联系人', icon: Paperclip },
}

/** 当事人我方/对方徽章文案（side 来自后端 Client.is_our_client） */
export const SIDE_LABEL = { ours: '我方', opposing: '对方' } as const

/** 输入防抖间隔（ms）：输入即搜，但请求攒一撮再发，避免每次按键都重排结果列表 */
export const DEBOUNCE_MS = 250

/** 全局检索 query key 前缀（面板独用，完整 key 为 [前缀, 检索词]） */
export const GLOBAL_SEARCH_KEY = 'global-search'
