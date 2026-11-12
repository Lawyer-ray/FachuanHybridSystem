import { createApiClient } from '@/lib/api'
import type { components } from '@/types/api-schema'

/* ============ 项目（委托合同）检索：生成链接时绑定项目用 ============ */

/** 跨 feature import workbench 被禁止，这里按需直连同源端点做最小投影 */
export const contractsApi = createApiClient({ prefix: '/api/v1/contracts' })

/** 合同检索命中行（生成物 ContractOut 的消费子集；id 覆写为必有） */
export type ContractHit = Pick<
  components['schemas']['ContractOut'],
  'name' | 'filing_number'
> & { id: number }

export async function searchContracts(q: string, signal?: AbortSignal): Promise<ContractHit[]> {
  if (!q.trim()) return []
  const res = await contractsApi
    .get('contracts', {
      searchParams: { search: q, slim: 'true', include_facets: 'false', page: '1', page_size: '10' },
      signal,
    })
    .json<{ items: ContractHit[] }>()
  return res.items ?? []
}
