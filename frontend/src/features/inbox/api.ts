/**
 * 收件箱 API
 */

import { api } from '@/lib/api'
import type { InboxMessage, InboxMessageDetail, InboxListParams } from './types'

const inboxApi_ = api.extend({
  prefixUrl: 'http://localhost:8002/api/v1/inbox',
})

/** 附件 URL 基础路径 */
const ATTACHMENT_BASE = 'http://localhost:8002/api/v1/inbox/messages'

export const inboxApi = {
  list: async (params?: InboxListParams): Promise<InboxMessage[]> => {
    const sp = new URLSearchParams()
    if (params?.source_id !== undefined) sp.set('source_id', String(params.source_id))
    if (params?.has_attachments !== undefined) sp.set('has_attachments', String(params.has_attachments))
    if (params?.search) sp.set('search', params.search)
    return inboxApi_.get('messages', { searchParams: sp }).json<InboxMessage[]>()
  },

  get: async (id: number | string): Promise<InboxMessageDetail> =>
    inboxApi_.get(`messages/${id}`).json<InboxMessageDetail>(),

  /** 生成附件下载 URL（需要前端拼 token） */
  attachmentDownloadUrl: (messageId: number, partIndex: number): string =>
    `${ATTACHMENT_BASE}/${messageId}/attachments/${partIndex}/download`,

  /** 生成附件预览 URL */
  attachmentPreviewUrl: (messageId: number, partIndex: number): string =>
    `${ATTACHMENT_BASE}/${messageId}/attachments/${partIndex}/preview`,
}

export default inboxApi
