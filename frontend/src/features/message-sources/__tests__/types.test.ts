/**
 * Message Sources Types Tests
 * 测试消息源模块的标签映射完整性
 */

import { SOURCE_TYPE_LABELS, SYNC_STATUS_LABELS } from '../types'
import type { SourceType, SyncStatus } from '../types'

const SOURCE_TYPE_VALUES: SourceType[] = ['imap', 'court_inbox', 'court_schedule']
const SYNC_STATUS_VALUES: SyncStatus[] = ['pending', 'success', 'failed']

describe('SOURCE_TYPE_LABELS', () => {
  it('maps every SourceType to a non-empty string', () => {
    for (const val of SOURCE_TYPE_VALUES) {
      expect(SOURCE_TYPE_LABELS[val]).toBeTruthy()
      expect(typeof SOURCE_TYPE_LABELS[val]).toBe('string')
    }
  })

  it('has 3 entries', () => {
    expect(Object.keys(SOURCE_TYPE_LABELS)).toHaveLength(3)
  })

  it('uses Chinese labels', () => {
    expect(SOURCE_TYPE_LABELS.imap).toBe('IMAP 邮箱')
    expect(SOURCE_TYPE_LABELS.court_inbox).toBe('一张网收件箱')
    expect(SOURCE_TYPE_LABELS.court_schedule).toBe('一张网庭审日程')
  })
})

describe('SYNC_STATUS_LABELS', () => {
  it('maps every SyncStatus to a non-empty string', () => {
    for (const val of SYNC_STATUS_VALUES) {
      expect(SYNC_STATUS_LABELS[val]).toBeTruthy()
      expect(typeof SYNC_STATUS_LABELS[val]).toBe('string')
    }
  })

  it('has 3 entries', () => {
    expect(Object.keys(SYNC_STATUS_LABELS)).toHaveLength(3)
  })

  it('uses Chinese labels', () => {
    expect(SYNC_STATUS_LABELS.pending).toBe('待同步')
    expect(SYNC_STATUS_LABELS.success).toBe('同步成功')
    expect(SYNC_STATUS_LABELS.failed).toBe('同步失败')
  })
})
