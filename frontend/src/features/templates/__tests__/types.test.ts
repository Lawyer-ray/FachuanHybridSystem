/**
 * Templates Types Tests
 * 测试模板模块的标签映射完整性
 */

import {
  TEMPLATE_TYPE_LABELS,
  CONTRACT_SUB_TYPE_LABELS,
  CASE_SUB_TYPE_LABELS,
  ARCHIVE_SUB_TYPE_LABELS,
} from '../types'
import type { TemplateType } from '../types'

const TEMPLATE_TYPE_VALUES: TemplateType[] = ['contract', 'case', 'archive']

describe('TEMPLATE_TYPE_LABELS', () => {
  it('maps every TemplateType to a non-empty string', () => {
    for (const val of TEMPLATE_TYPE_VALUES) {
      expect(TEMPLATE_TYPE_LABELS[val]).toBeTruthy()
      expect(typeof TEMPLATE_TYPE_LABELS[val]).toBe('string')
    }
  })

  it('has 3 entries', () => {
    expect(Object.keys(TEMPLATE_TYPE_LABELS)).toHaveLength(3)
  })

  it('uses Chinese labels', () => {
    expect(TEMPLATE_TYPE_LABELS.contract).toBe('合同文件模板')
    expect(TEMPLATE_TYPE_LABELS.case).toBe('案件文件模板')
    expect(TEMPLATE_TYPE_LABELS.archive).toBe('归档文件模板')
  })
})

describe('CONTRACT_SUB_TYPE_LABELS', () => {
  it('defines labels for contract sub-types', () => {
    expect(CONTRACT_SUB_TYPE_LABELS.contract).toBe('合同模板')
    expect(CONTRACT_SUB_TYPE_LABELS.supplementary_agreement).toBe('补充协议模板')
  })

  it('has 2 entries', () => {
    expect(Object.keys(CONTRACT_SUB_TYPE_LABELS)).toHaveLength(2)
  })
})

describe('CASE_SUB_TYPE_LABELS', () => {
  it('defines labels for all case sub-types', () => {
    expect(CASE_SUB_TYPE_LABELS.pleading_materials).toBe('诉状材料')
    expect(CASE_SUB_TYPE_LABELS.evidence_materials).toBe('证据材料')
    expect(CASE_SUB_TYPE_LABELS.power_of_attorney_materials).toBe('授权委托材料')
    expect(CASE_SUB_TYPE_LABELS.property_preservation_materials).toBe('财产保全材料')
    expect(CASE_SUB_TYPE_LABELS.service_address_materials).toBe('送达地址材料')
    expect(CASE_SUB_TYPE_LABELS.refund_account_materials).toBe('收款退费账户材料')
    expect(CASE_SUB_TYPE_LABELS.application_materials).toBe('申请材料')
    expect(CASE_SUB_TYPE_LABELS.other_materials).toBe('其他材料')
  })

  it('has 8 entries', () => {
    expect(Object.keys(CASE_SUB_TYPE_LABELS)).toHaveLength(8)
  })
})

describe('ARCHIVE_SUB_TYPE_LABELS', () => {
  it('defines labels for all archive sub-types', () => {
    expect(ARCHIVE_SUB_TYPE_LABELS.case_cover).toBe('案卷封面')
    expect(ARCHIVE_SUB_TYPE_LABELS.closing_archive_register).toBe('结案归档登记表')
    expect(ARCHIVE_SUB_TYPE_LABELS.inner_catalog).toBe('卷内目录')
    expect(ARCHIVE_SUB_TYPE_LABELS.lawyer_work_log).toBe('律师工作日志')
    expect(ARCHIVE_SUB_TYPE_LABELS.service_quality_card).toBe('办案服务质量监督卡')
    expect(ARCHIVE_SUB_TYPE_LABELS.case_summary).toBe('办案小结')
  })

  it('has 6 entries', () => {
    expect(Object.keys(ARCHIVE_SUB_TYPE_LABELS)).toHaveLength(6)
  })
})
