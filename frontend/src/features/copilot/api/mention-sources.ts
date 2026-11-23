/**
 * `@` 引用的跨实体候选源（core 全局搜索）。
 *
 * 从 `api.ts` 拆出：端点前缀是 `search/`（core 域），与 copilot 会话无关。
 * `api.ts` 仍 re-export，既有 import 路径不变。
 */

import { api } from '@/lib/api'

import type { GlobalSearchResult } from './search-types'

/**
 * 跨实体关键词搜索。契约：`backend/apps/core/api/search_api.py:52`
 * `GET /search?q=&limit=`（前缀 `/search` 见 api.py:320）。
 *
 * `q` 为空时后端直接回空（不是错误）；`limit` 服务端硬顶 10。
 */
export function globalSearch(q: string, limit = 5, signal?: AbortSignal): Promise<GlobalSearchResult> {
  return api.get('search', { searchParams: { q, limit }, ...(signal ? { signal } : {}) }).json<GlobalSearchResult>()
}
