/**
 * 财产保全询价表单验证 Schema
 * @module preservation-quotes/schemas
 *
 * 验证规则：
 * - preserve_amount: 必填，正数
 * - corp_id: 必填，非空字符串
 * - category_id: 必填，非空字符串
 * - credential_id: 必填，正整数
 *
 * @validates Requirements 3.2, 3.3, 3.4, 3.5
 */

import { z } from 'zod'

// ============================================================================
// 表单验证 Schema
// ============================================================================

/**
 * 创建询价表单验证 Schema
 *
 * @validates Requirements 3.2 - 保全金额必填，正数
 * @validates Requirements 3.3 - 企业选择必填
 * @validates Requirements 3.4 - 类别选择必填
 * @validates Requirements 3.5 - 凭证选择必填
 */
export const quoteCreateSchema = z.object({
  /** 保全金额 - 必填，必须大于0 */
  preserve_amount: z
    .number({ error: '请输入保全金额' })
    .positive('保全金额必须大于0'),

  /** 企业 ID - 必填 */
  corp_id: z
    .string({ error: '请选择企业' })
    .min(1, '请选择企业'),

  /** 类别 ID - 必填 */
  category_id: z
    .string({ error: '请选择类别' })
    .min(1, '请选择类别'),

  /** 凭证 ID - 必填，正整数 */
  credential_id: z
    .number({ error: '请选择凭证' })
    .int('凭证ID必须为整数')
    .positive('请选择凭证'),
})

// ============================================================================
// 类型导出
// ============================================================================

/**
 * 创建询价表单数据类型
 * 从 Zod Schema 推断
 */
export type QuoteCreateFormData = z.infer<typeof quoteCreateSchema>
