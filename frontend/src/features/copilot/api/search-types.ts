/**
 * `@` 引用候选源用的全局搜索返回契约（core `search/` 域）。
 *
 * 从 `api/mention-sources.ts` 拆出：类型由 `api.ts` re-export 回既有 import
 * 路径（`from '../api'`），取数函数仍留在原文件。
 */

/** 全局搜索的一条结果（`core/api/search_api.py` 的 `SearchResultItem`） */
export interface GlobalSearchItem {
  id: number
  title: string
  subtitle: string
  // 与生成物 `SearchResultItem`（api-schema.d.ts）对齐：side 是三值枚举、contract_id 可缺省。
  // 手抄成 `string` / 必填会静默丢掉契约约束（审计 P05-101）。
  side: 'ours' | 'opposing' | ''
  case_type: string
  contract_id?: number | null
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
