import { createApiClient } from '@/lib/api'
import type { ClientHit } from '../types'

/** 客户/当事人检索（/api/v1/client/parties/search，精简字段，兼容证件档案为空的客户） */
export const clientApi = createApiClient({ prefix: '/api/v1/client' })

/**
 * 按关键字模糊检索当事人。
 * isOurClient 限定范围：委托人传 true（我方当事人）、对方当事人传 false。
 */
export async function searchClients(
  keyword: string,
  isOurClient: boolean,
  signal?: AbortSignal,
): Promise<ClientHit[]> {
  return clientApi
    .get('parties/search', {
      searchParams: { keyword, is_our_client: isOurClient ? 'true' : 'false' },
      signal,
    })
    .json<ClientHit[]>()
}

/**
 * 按关键字在客户库检索，**不限**我方/对方（不传 is_our_client，两侧一起返回）。
 *
 * 与 `searchClients` 的唯一差别就是不加侧过滤 —— 因为自动识别当事人要回答的
 * 正是「这个人属于哪一侧」：先按侧过滤等于先把答案当成输入了。
 * 服务端 `is_our_client` 是可选参数（见 /client/parties/search），省略即不过滤。
 */
export async function lookupClients(keyword: string, signal?: AbortSignal): Promise<ClientHit[]> {
  return clientApi
    .get('parties/search', { searchParams: { keyword }, signal })
    .json<ClientHit[]>()
}
