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
