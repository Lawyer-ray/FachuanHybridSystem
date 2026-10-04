import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'
import type { CategoryKey, Hit } from './types'

/** 后端已有现成接口：GET /api/v1/search?q=，跨 6 类实体并发搜索
 *  （客户 / 案件 / 合同 / 收件箱 / 法院短信 / 联系人），每类最多 10 条。 */
const searchApi = createApiClient({ prefix: '/api/v1/search' })

/** 类别固定顺序：结果拉平与筛选标签展示共用 */
export const CATEGORY_ORDER: readonly CategoryKey[] = [
  'cases',
  'clients',
  'contracts',
  'inbox',
  'court_sms',
  'contacts',
]

/** GET /api/v1/search 的响应（生成物 GlobalSearchResult，六类 key 与 CATEGORY_ORDER 一一对应） */
type GlobalSearchResponse = components['schemas']['GlobalSearchResult']

/** 按固定类别顺序把各类命中拉平成统一列表 */
export async function runSearch(q: string): Promise<Hit[]> {
  const res = await searchApi
    .get('', { searchParams: { q, limit: 8 } })
    .json<GlobalSearchResponse>()
  const out: Hit[] = []
  for (const cat of CATEGORY_ORDER) {
    for (const it of res[cat] ?? []) {
      out.push({ category: cat, id: it.id, title: it.title, subtitle: it.subtitle })
    }
  }
  return out
}
