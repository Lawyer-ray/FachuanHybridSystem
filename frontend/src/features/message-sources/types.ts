export type SourceType = 'imap' | 'court_inbox' | 'court_schedule'

export const SOURCE_TYPE_LABELS: Record<SourceType, string> = {
  imap: 'IMAP 邮箱',
  court_inbox: '一张网收件箱',
  court_schedule: '一张网庭审日程',
}

export type SyncStatus = 'pending' | 'success' | 'failed'

export const SYNC_STATUS_LABELS: Record<SyncStatus, string> = {
  pending: '待同步',
  success: '同步成功',
  failed: '同步失败',
}

export interface MessageSource {
  id: number
  display_name: string
  source_type: SourceType
  credential_account: string
  is_enabled: boolean
  poll_interval_minutes: number
  last_sync_at: string | null
  last_sync_status: SyncStatus
  created_at: string
}
