/**
 * Contract Types Tests
 * 测试合同模块的枚举标签映射完整性
 */

import {
  CASE_TYPE_LABELS,
  CONTRACT_STATUS_LABELS,
  FEE_MODE_LABELS,
  INVOICE_STATUS_LABELS,
  PARTY_ROLE_LABELS,
  MATERIAL_CATEGORY_LABELS,
} from '../types'
import type { CaseType, ContractStatus, FeeMode, InvoiceStatus, PartyRole, MaterialCategory } from '../types'

const CASE_TYPE_VALUES: CaseType[] = ['civil', 'criminal', 'administrative', 'labor', 'intl', 'special', 'advisor']
const CONTRACT_STATUS_VALUES: ContractStatus[] = ['unsigned', 'active', 'closed', 'archived']
const FEE_MODE_VALUES: FeeMode[] = ['FIXED', 'SEMI_RISK', 'FULL_RISK', 'CUSTOM']
const INVOICE_STATUS_VALUES: InvoiceStatus[] = ['UNINVOICED', 'INVOICED_PARTIAL', 'INVOICED_FULL']
const PARTY_ROLE_VALUES: PartyRole[] = ['PRINCIPAL', 'BENEFICIARY', 'OPPOSING']
const MATERIAL_CATEGORY_VALUES: MaterialCategory[] = [
  'contract_original', 'supplementary_agreement', 'invoice',
  'archive_doc', 'supervision_card', 'auth_doc', 'other',
]

function checkLabels(labels: Record<string, string>, values: readonly string[]) {
  for (const val of values) {
    expect(labels[val]).toBeDefined()
    expect(typeof labels[val]).toBe('string')
    expect(labels[val].length).toBeGreaterThan(0)
  }
}

describe('CASE_TYPE_LABELS', () => {
  it('maps every CaseType to a non-empty string', () => {
    checkLabels(CASE_TYPE_LABELS, CASE_TYPE_VALUES)
  })

  it('has 7 entries', () => {
    expect(Object.keys(CASE_TYPE_LABELS)).toHaveLength(7)
  })
})

describe('CONTRACT_STATUS_LABELS', () => {
  it('maps every ContractStatus to a non-empty string', () => {
    checkLabels(CONTRACT_STATUS_LABELS, CONTRACT_STATUS_VALUES)
  })

  it('has 4 entries', () => {
    expect(Object.keys(CONTRACT_STATUS_LABELS)).toHaveLength(4)
  })
})

describe('FEE_MODE_LABELS', () => {
  it('maps every FeeMode to a non-empty string', () => {
    checkLabels(FEE_MODE_LABELS, FEE_MODE_VALUES)
  })

  it('has 4 entries', () => {
    expect(Object.keys(FEE_MODE_LABELS)).toHaveLength(4)
  })
})

describe('INVOICE_STATUS_LABELS', () => {
  it('maps every InvoiceStatus to a non-empty string', () => {
    checkLabels(INVOICE_STATUS_LABELS, INVOICE_STATUS_VALUES)
  })

  it('has 3 entries', () => {
    expect(Object.keys(INVOICE_STATUS_LABELS)).toHaveLength(3)
  })
})

describe('PARTY_ROLE_LABELS', () => {
  it('maps every PartyRole to a non-empty string', () => {
    checkLabels(PARTY_ROLE_LABELS, PARTY_ROLE_VALUES)
  })

  it('has 3 entries', () => {
    expect(Object.keys(PARTY_ROLE_LABELS)).toHaveLength(3)
  })
})

describe('MATERIAL_CATEGORY_LABELS', () => {
  it('maps every MaterialCategory to a non-empty string', () => {
    checkLabels(MATERIAL_CATEGORY_LABELS, MATERIAL_CATEGORY_VALUES)
  })

  it('has 7 entries', () => {
    expect(Object.keys(MATERIAL_CATEGORY_LABELS)).toHaveLength(7)
  })
})
