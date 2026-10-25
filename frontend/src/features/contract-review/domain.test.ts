import { describe, expect, it } from 'vitest'
import {
  bucketRevisions,
  countBySeverity,
  progressText,
  revisedFileName,
  severityLabel,
} from './domain'
import type { ReviewRevision } from './types'

function rev(over: Partial<ReviewRevision> = {}): ReviewRevision {
  return {
    id: 'r1',
    ordinal: 0,
    kind: 'risk',
    severity: 'high',
    title: '',
    original: '原文',
    suggested: '改法',
    reason: '依据',
    paragraph_index: 0,
    status: 'pending',
    reject_reason: '',
    ...over,
  }
}

describe('bucketRevisions', () => {
  it('待决策按「严重度 → 原顺序」，先看高危', () => {
    const items = [
      rev({ id: 'a', ordinal: 0, severity: 'low' }),
      rev({ id: 'b', ordinal: 1, severity: 'high' }),
      rev({ id: 'c', ordinal: 2, severity: 'high' }),
      rev({ id: 'd', ordinal: 3, severity: 'medium' }),
    ]
    const { pending } = bucketRevisions(items)
    expect(pending.map((r) => r.id)).toEqual(['b', 'c', 'd', 'a'])
  })

  it('已处理沉底且按原顺序（保留律师的工作轨迹）', () => {
    const items = [
      rev({ id: 'a', ordinal: 2, status: 'accepted' }),
      rev({ id: 'b', ordinal: 0, status: 'rejected' }),
      rev({ id: 'c', ordinal: 1, status: 'pending' }),
    ]
    const { pending, decided } = bucketRevisions(items)
    expect(pending.map((r) => r.id)).toEqual(['c'])
    expect(decided.map((r) => r.id)).toEqual(['b', 'a'])
  })

  it('空清单不炸', () => {
    expect(bucketRevisions([])).toEqual({ pending: [], decided: [] })
  })
})

describe('countBySeverity', () => {
  it('只数待决策的（已处理不再进风险统计）', () => {
    const items = [
      rev({ id: 'a', severity: 'high' }),
      rev({ id: 'b', severity: 'high', status: 'accepted' }),
      rev({ id: 'c', severity: 'medium' }),
      rev({ id: 'd', severity: 'low' }),
      rev({ id: 'e', severity: '' }),
    ]
    expect(countBySeverity(items)).toEqual({ high: 1, medium: 1, low: 1 })
  })
})

describe('severityLabel', () => {
  it('映射高/中/低，空值不产出标签', () => {
    expect(severityLabel('high')).toBe('高')
    expect(severityLabel('medium')).toBe('中')
    expect(severityLabel('low')).toBe('低')
    expect(severityLabel('')).toBe('')
  })
})

describe('revisedFileName', () => {
  const day = new Date('2026-10-24T10:00:00')

  it('按律师磁盘命名规律生成修订版名', () => {
    expect(revisedFileName('装修工程合同.docx', 1, day)).toBe('装修工程合同[修订版]V1_20261024.docx')
  })

  it('已有 [修订版] 后缀先剥掉，避免叠加', () => {
    expect(revisedFileName('装修工程合同[修订版]V1_20261009.docx', 2, day)).toBe(
      '装修工程合同[修订版]V2_20261024.docx',
    )
  })

  it('客户回稿的 [甲方修订版] 也能正确剥掉', () => {
    expect(revisedFileName('合同[甲方修订版]V1_20261010.docx', 3, day)).toBe(
      '合同[修订版]V3_20261024.docx',
    )
  })

  it('无后缀的文件名同样可用', () => {
    expect(revisedFileName('合同', 1, day)).toBe('合同[修订版]V1_20261024.docx')
  })
})

describe('progressText', () => {
  it('已处理 / 共 N', () => {
    expect(progressText(8, 3)).toBe('已处理 5 / 共 8')
    expect(progressText(0, 0)).toBe('已处理 0 / 共 0')
  })
})
