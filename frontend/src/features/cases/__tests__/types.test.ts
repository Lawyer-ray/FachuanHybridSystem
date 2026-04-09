/**
 * Property 1: 枚举标签双语完整性
 *
 * For any 枚举类型中的每一个值，对应的 LABELS 常量中都应存在包含
 * zh 和 en 两个非空字符串字段的条目。
 *
 * Feature: admin-cases-frontend, Property 1: 枚举标签双语完整性
 * Validates: Requirements 1.2, 8.2
 */

import { describe, it, expect } from 'vitest'
import fc from 'fast-check'

import {
  SIMPLE_CASE_TYPE_LABELS,
  CASE_STATUS_LABELS,
  CASE_STAGE_LABELS,
  LEGAL_STATUS_LABELS,
  AUTHORITY_TYPE_LABELS,
  CASE_LOG_REMINDER_TYPE_LABELS,
} from '../types'

// All enum value arrays
const SIMPLE_CASE_TYPE_VALUES = ['civil', 'administrative', 'criminal', 'execution', 'bankruptcy'] as const
const CASE_STATUS_VALUES = ['active', 'closed'] as const
const CASE_STAGE_VALUES = [
  'first_trial', 'second_trial', 'enforcement', 'labor_arbitration',
  'administrative_review', 'private_prosecution', 'investigation',
  'prosecution_review', 'retrial_first', 'retrial_second', 'apply_retrial',
  'rehearing_first', 'rehearing_second', 'review', 'death_penalty_review',
  'petition', 'apply_protest', 'petition_protest',
] as const
const LEGAL_STATUS_VALUES = [
  'plaintiff', 'defendant', 'third', 'applicant', 'respondent',
  'criminal_defendant', 'victim', 'appellant', 'appellee',
  'orig_plaintiff', 'orig_defendant', 'orig_third',
] as const
const AUTHORITY_TYPE_VALUES = ['investigation', 'prosecution', 'trial', 'detention'] as const
const CASE_LOG_REMINDER_TYPE_VALUES = [
  'hearing', 'asset_preservation', 'evidence_deadline',
  'statute_limitations', 'appeal_period', 'other',
] as const

function checkLabels(labels: Record<string, { zh: string; en: string }>, values: readonly string[]) {
  for (const val of values) {
    const label = labels[val]
    expect(label).toBeDefined()
    expect(label.zh).toBeTruthy()
    expect(label.en).toBeTruthy()
    expect(typeof label.zh).toBe('string')
    expect(typeof label.en).toBe('string')
  }
}

describe('Property 1: 枚举标签双语完整性', () => {
  it('SimpleCaseType labels are complete with zh and en', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...SIMPLE_CASE_TYPE_VALUES),
        (val) => {
          const label = SIMPLE_CASE_TYPE_LABELS[val]
          return label !== undefined && label.zh.length > 0 && label.en.length > 0
        },
      ),
      { numRuns: 100 },
    )
  })

  it('CaseStatus labels are complete with zh and en', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...CASE_STATUS_VALUES),
        (val) => {
          const label = CASE_STATUS_LABELS[val]
          return label !== undefined && label.zh.length > 0 && label.en.length > 0
        },
      ),
      { numRuns: 100 },
    )
  })

  it('CaseStage labels are complete with zh and en', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...CASE_STAGE_VALUES),
        (val) => {
          const label = CASE_STAGE_LABELS[val]
          return label !== undefined && label.zh.length > 0 && label.en.length > 0
        },
      ),
      { numRuns: 100 },
    )
  })

  it('LegalStatus labels are complete with zh and en', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...LEGAL_STATUS_VALUES),
        (val) => {
          const label = LEGAL_STATUS_LABELS[val]
          return label !== undefined && label.zh.length > 0 && label.en.length > 0
        },
      ),
      { numRuns: 100 },
    )
  })

  it('AuthorityType labels are complete with zh and en', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...AUTHORITY_TYPE_VALUES),
        (val) => {
          const label = AUTHORITY_TYPE_LABELS[val]
          return label !== undefined && label.zh.length > 0 && label.en.length > 0
        },
      ),
      { numRuns: 100 },
    )
  })

  it('CaseLogReminderType labels are complete with zh and en', () => {
    fc.assert(
      fc.property(
        fc.constantFrom(...CASE_LOG_REMINDER_TYPE_VALUES),
        (val) => {
          const label = CASE_LOG_REMINDER_TYPE_LABELS[val]
          return label !== undefined && label.zh.length > 0 && label.en.length > 0
        },
      ),
      { numRuns: 100 },
    )
  })

  it('all label maps cover every enum value (exhaustive check)', () => {
    checkLabels(SIMPLE_CASE_TYPE_LABELS, SIMPLE_CASE_TYPE_VALUES)
    checkLabels(CASE_STATUS_LABELS, CASE_STATUS_VALUES)
    checkLabels(CASE_STAGE_LABELS, CASE_STAGE_VALUES)
    checkLabels(LEGAL_STATUS_LABELS, LEGAL_STATUS_VALUES)
    checkLabels(AUTHORITY_TYPE_LABELS, AUTHORITY_TYPE_VALUES)
    checkLabels(CASE_LOG_REMINDER_TYPE_LABELS, CASE_LOG_REMINDER_TYPE_VALUES)
  })
})
