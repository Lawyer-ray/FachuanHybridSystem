/**
 * Reminder Types Tests
 * 测试提醒类型标签映射的完整性
 */

import { REMINDER_TYPE_LABELS } from '../types'
import type { ReminderType } from '../types'

const REMINDER_TYPE_VALUES: ReminderType[] = [
  'hearing',
  'asset_preservation_expires',
  'evidence_deadline',
  'appeal_deadline',
  'statute_limitations',
  'payment_deadline',
  'submission_deadline',
  'other',
]

describe('REMINDER_TYPE_LABELS', () => {
  it('maps every ReminderType value to a non-empty string', () => {
    for (const val of REMINDER_TYPE_VALUES) {
      const label = REMINDER_TYPE_LABELS[val]
      expect(label).toBeDefined()
      expect(typeof label).toBe('string')
      expect(label.length).toBeGreaterThan(0)
    }
  })

  it('has exactly 8 entries', () => {
    expect(Object.keys(REMINDER_TYPE_LABELS)).toHaveLength(8)
  })

  it('uses Chinese labels', () => {
    expect(REMINDER_TYPE_LABELS.hearing).toBe('开庭')
    expect(REMINDER_TYPE_LABELS.asset_preservation_expires).toBe('财产保全到期日')
    expect(REMINDER_TYPE_LABELS.evidence_deadline).toBe('举证到期日')
    expect(REMINDER_TYPE_LABELS.appeal_deadline).toBe('上诉期到期日')
    expect(REMINDER_TYPE_LABELS.statute_limitations).toBe('诉讼时效到期日')
    expect(REMINDER_TYPE_LABELS.payment_deadline).toBe('缴费期限')
    expect(REMINDER_TYPE_LABELS.submission_deadline).toBe('补正/材料提交期限')
    expect(REMINDER_TYPE_LABELS.other).toBe('其他')
  })
})
