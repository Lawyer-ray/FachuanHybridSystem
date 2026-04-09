/**
 * 收件箱类型定义
 */

/** 附件元信息 */
export interface AttachmentMeta {
  filename: string
  size: number
  content_type: string
  part_index: number
}

/** 收件箱消息（列表项） */
export interface InboxMessage {
  id: number
  source_name: string
  source_type: string
  subject: string
  sender: string
  recipient: string
  received_at: string
  has_attachments: boolean
  attachment_count: number
  created_at: string
}

/** 收件箱消息详情 */
export interface InboxMessageDetail extends InboxMessage {
  body_text: string
  body_html: string
  attachments: AttachmentMeta[]
}

/** 列表查询参数 */
export interface InboxListParams {
  source_id?: number
  has_attachments?: boolean
  search?: string
}
