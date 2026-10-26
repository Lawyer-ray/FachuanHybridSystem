import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'
import type { CategoryKey, Hit } from './types'

/** 后端已有现成接口：GET /api/v1/search?q=，跨 6 类实体并发搜索
 *  （当事人 / 案件 / 合同 / 收件箱 / 法院短信 / 联系人），每类最多 10 条。
 *  前端项目语义把「合同 + 案件」融合成一类 projects（项目 = 委托合同，案件挂在合同下）。 */
const searchApi = createApiClient({ prefix: '/api/v1/search' })

/** 类别固定顺序：结果拉平与筛选标签展示共用（projects 在首） */
export const CATEGORY_ORDER: readonly CategoryKey[] = ['projects', 'clients', 'inbox', 'court_sms', 'contacts']

/** GET /api/v1/search 的响应（生成物 GlobalSearchResult，六类 key 与后端一一对应） */
type GlobalSearchResponse = components['schemas']['GlobalSearchResult']

/** 后端数组项 → 统一 Hit（缺字段兜底与旧后端兼容） */
function toHit(category: string, it: NonNullable<GlobalSearchResponse['cases']>[number]): Hit {
  return {
    category,
    id: it.id,
    title: it.title,
    subtitle: it.subtitle ?? '',
    side: it.side ?? '',
    case_type: it.case_type ?? '',
    contract_id: it.contract_id ?? null,
    contract_name: it.contract_name ?? '',
  }
}

/** 按固定类别顺序把各类命中拉平成统一列表（合同命中在前、案件命中紧随，组内渲染再归组） */
export async function runSearch(q: string): Promise<Hit[]> {
  const res = await searchApi
    .get('', { searchParams: { q, limit: 8 } })
    .json<GlobalSearchResponse>()
  const out: Hit[] = []
  // 项目类：合同命中 = 项目行；案件命中带 contract_id/name/case_type，前端挂到所属项目下
  for (const c of res.contracts ?? []) out.push({ ...toHit('projects', c), kind: 'contract' })
  for (const c of res.cases ?? []) out.push({ ...toHit('projects', c), kind: 'case' })
  for (const cat of ['clients', 'inbox', 'court_sms', 'contacts'] as const) {
    for (const it of res[cat] ?? []) out.push(toHit(cat, it))
  }
  return out
}
