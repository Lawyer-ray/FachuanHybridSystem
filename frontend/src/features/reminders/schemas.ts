/**
 * Reminder Form Validation Schemas
 * 重要日期提醒表单验证 Schema
 *
 * @module features/reminders/schemas
 */

import { z } from 'zod'

// ============================================================================
// 表单验证 Schema
// ============================================================================

/**
 * 提醒表单验证 Schema
 *
 * 验证规则：
 * - reminder_type: 必填，不能为空字符串
 * - content: 必填，1-255 字符
 * - due_at: 必填，有效日期
 * - contract_id/case_log_id: 二选一必填
 *
 * @validates Requirements 7.1, 7.2, 7.3, 7.4
 */
export const reminderFormSchema = z
  .object({
    /** 提醒类型 - 必填 */
    reminder_type: z.string().min(1, '请选择提醒类型'),

    /** 提醒内容 - 必填，最多255字符 */
    content: z
      .string()
      .min(1, '请输入提醒事项')
      .max(255, '提醒事项不能超过255字符'),

    /** 到期时间 - 必填 */
    due_at: z.date({ required_error: '请选择到期时间' }),

    /** 关联合同 ID - 与 case_log_id 二选一 */
    contract_id: z.number().nullable().optional(),

    /** 关联案件日志 ID - 与 contract_id 二选一 */
    case_log_id: z.number().nullable().optional(),

    /** 元数据 - 可选 */
    metadata: z.record(z.unknown()).optional(),
  })
  .refine(
    (data) => {
      const hasContract = data.contract_id != null && data.contract_id !== 0
      const hasCaseLog = data.case_log_id != null && data.case_log_id !== 0
      // XOR: 必须且只能有一个为真
      return hasContract !== hasCaseLog
    },
    {
      message: '必须且只能关联合同或案件日志之一',
      path: ['contract_id'],
    }
  )

// ============================================================================
// 类型导出
// ============================================================================

/**
 * 提醒表单数据类型
 * 从 Zod Schema 推断
 */
export type ReminderFormData = z.infer<typeof reminderFormSchema>
