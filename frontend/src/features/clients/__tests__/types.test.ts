/**
 * Client Types Tests
 * 测试当事人模块的枚举标签和常量
 */

import {
  CLIENT_TYPE_LABELS,
  DOC_TYPE_LABELS,
  NATURAL_DOC_TYPES,
  LEGAL_DOC_TYPES,
  CLUE_TYPE_LABELS,
} from '../types'
import type { ClientType, DocType, ClueType } from '../types'

const CLIENT_TYPE_VALUES: ClientType[] = ['natural', 'legal', 'non_legal_org']

const DOC_TYPE_VALUES: DocType[] = [
  'id_card', 'passport', 'hk_macao_permit', 'residence_permit',
  'household_register', 'business_license', 'legal_rep_id_card',
]

const CLUE_TYPE_VALUES: ClueType[] = ['bank', 'alipay', 'wechat', 'real_estate', 'other']

describe('CLIENT_TYPE_LABELS', () => {
  it('maps every ClientType to a non-empty string', () => {
    for (const val of CLIENT_TYPE_VALUES) {
      expect(CLIENT_TYPE_LABELS[val]).toBeTruthy()
      expect(typeof CLIENT_TYPE_LABELS[val]).toBe('string')
    }
  })

  it('has 3 entries', () => {
    expect(Object.keys(CLIENT_TYPE_LABELS)).toHaveLength(3)
  })

  it('uses Chinese labels', () => {
    expect(CLIENT_TYPE_LABELS.natural).toBe('自然人')
    expect(CLIENT_TYPE_LABELS.legal).toBe('法人')
    expect(CLIENT_TYPE_LABELS.non_legal_org).toBe('非法人组织')
  })
})

describe('DOC_TYPE_LABELS', () => {
  it('maps every DocType to a non-empty string', () => {
    for (const val of DOC_TYPE_VALUES) {
      expect(DOC_TYPE_LABELS[val]).toBeTruthy()
      expect(typeof DOC_TYPE_LABELS[val]).toBe('string')
    }
  })

  it('has 7 entries', () => {
    expect(Object.keys(DOC_TYPE_LABELS)).toHaveLength(7)
  })
})

describe('NATURAL_DOC_TYPES', () => {
  it('contains 5 document types for natural persons', () => {
    expect(NATURAL_DOC_TYPES).toHaveLength(5)
  })

  it('includes id_card', () => {
    expect(NATURAL_DOC_TYPES).toContain('id_card')
  })

  it('does not include business_license', () => {
    expect(NATURAL_DOC_TYPES).not.toContain('business_license')
  })
})

describe('LEGAL_DOC_TYPES', () => {
  it('contains 7 document types for legal entities', () => {
    expect(LEGAL_DOC_TYPES).toHaveLength(7)
  })

  it('includes business_license', () => {
    expect(LEGAL_DOC_TYPES).toContain('business_license')
  })

  it('includes legal_rep_id_card', () => {
    expect(LEGAL_DOC_TYPES).toContain('legal_rep_id_card')
  })
})

describe('CLUE_TYPE_LABELS', () => {
  it('maps every ClueType to a non-empty string', () => {
    for (const val of CLUE_TYPE_VALUES) {
      expect(CLUE_TYPE_LABELS[val]).toBeTruthy()
      expect(typeof CLUE_TYPE_LABELS[val]).toBe('string')
    }
  })

  it('has 5 entries', () => {
    expect(Object.keys(CLUE_TYPE_LABELS)).toHaveLength(5)
  })

  it('uses Chinese labels', () => {
    expect(CLUE_TYPE_LABELS.bank).toBe('银行账户')
    expect(CLUE_TYPE_LABELS.alipay).toBe('支付宝账户')
    expect(CLUE_TYPE_LABELS.wechat).toBe('微信账户')
    expect(CLUE_TYPE_LABELS.real_estate).toBe('不动产')
    expect(CLUE_TYPE_LABELS.other).toBe('其他')
  })
})
