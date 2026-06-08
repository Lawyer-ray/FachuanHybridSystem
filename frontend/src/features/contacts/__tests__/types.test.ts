/**
 * Contacts Types Tests
 * 测试联系人角色标签映射的完整性
 */

import { CONTACT_ROLE_LABELS } from '../types'
import type { ContactRole } from '../types'

const CONTACT_ROLE_VALUES: ContactRole[] = [
  'presiding_judge', 'judge', 'clerk', 'judge_assistant',
  'prosecutor', 'police', 'arbitrator', 'mediator', 'other',
]

describe('CONTACT_ROLE_LABELS', () => {
  it('maps every ContactRole to a label with zh and en', () => {
    for (const val of CONTACT_ROLE_VALUES) {
      const label = CONTACT_ROLE_LABELS[val]
      expect(label).toBeDefined()
      expect(label.zh).toBeTruthy()
      expect(label.en).toBeTruthy()
      expect(typeof label.zh).toBe('string')
      expect(typeof label.en).toBe('string')
    }
  })

  it('has exactly 9 entries', () => {
    expect(Object.keys(CONTACT_ROLE_LABELS)).toHaveLength(9)
  })

  it('provides correct Chinese labels', () => {
    expect(CONTACT_ROLE_LABELS.presiding_judge.zh).toBe('审判长')
    expect(CONTACT_ROLE_LABELS.judge.zh).toBe('审判员/法官')
    expect(CONTACT_ROLE_LABELS.clerk.zh).toBe('书记员')
    expect(CONTACT_ROLE_LABELS.judge_assistant.zh).toBe('法官助理')
    expect(CONTACT_ROLE_LABELS.prosecutor.zh).toBe('检察官')
    expect(CONTACT_ROLE_LABELS.police.zh).toBe('警官')
    expect(CONTACT_ROLE_LABELS.arbitrator.zh).toBe('仲裁员')
    expect(CONTACT_ROLE_LABELS.mediator.zh).toBe('调解员')
    expect(CONTACT_ROLE_LABELS.other.zh).toBe('其他')
  })

  it('provides correct English labels', () => {
    expect(CONTACT_ROLE_LABELS.presiding_judge.en).toBe('Presiding Judge')
    expect(CONTACT_ROLE_LABELS.judge.en).toBe('Judge')
    expect(CONTACT_ROLE_LABELS.clerk.en).toBe('Clerk')
    expect(CONTACT_ROLE_LABELS.other.en).toBe('Other')
  })
})
