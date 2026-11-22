/**
 * `@` 引用的跨实体候选源（core 全局搜索）。
 *
 * 从 `api.ts` 拆出：端点前缀是 `search/`（core 域），与 copilot 会话无关。
 * `api.ts` 仍 re-export，既有 import 路径不变。
 */

import { api } from '@/lib/api'

/** 全局搜索的一条结果（`core/api/search_api.py` 的 `SearchResultItem`） */
export interface GlobalSearchItem {
  id: number
  title: string
  subtitle: string
  side: string
  case_type: string
  contract_id: number | null
  contract_name: string
}

/**
 * `GET /search` 的返回（`GlobalSearchResult`）：六类固定键，本前端只用两类的标题/副标题。
 *
 * 为什么用全局搜索做 `@案件` / `@合同` 的候选源：它不是为引用写的，但它是**唯一**
 * 按关键词跨案件/合同检索、且已做行级 ACL 过滤的端点（`search_service.py` 每条
 * search_* 都接 user/org_access）。单类列表端点（`GET /cases`）要自己拼过滤词，
 * 且搜索口径会与全局搜索漂移。
 */
export interface GlobalSearchResult {
  clients: GlobalSearchItem[]
  cases: GlobalSearchItem[]
  contracts: GlobalSearchItem[]
  inbox: GlobalSearchItem[]
  court_sms: GlobalSearchItem[]
  contacts: GlobalSearchItem[]
}

/**
 * 跨实体关键词搜索。契约：`backend/apps/core/api/search_api.py:52`
 * `GET /search?q=&limit=`（前缀 `/search` 见 api.py:320）。
 *
 * `q` 为空时后端直接回空（不是错误）；`limit` 服务端硬顶 10。
 */
export function globalSearch(q: string, limit = 5, signal?: AbortSignal): Promise<GlobalSearchResult> {
  return api.get('search', { searchParams: { q, limit }, ...(signal ? { signal } : {}) }).json<GlobalSearchResult>()
}
