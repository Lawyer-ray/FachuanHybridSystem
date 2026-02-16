/**
 * 文书智能识别表单验证 Schema
 * @module document-recognition/schemas
 *
 * 验证规则：
 * - 手动绑定：case_id 必填
 * - 文件上传：类型限制 PDF/图片，大小限制 10MB
 *
 * @validates Requirements 6.2, 6.3
 */

import { z } from 'zod'
import { ACCEPTED_FILE_TYPES, MAX_FILE_SIZE } from '../constants'

// ============================================================================
// 表单验证 Schema
// ============================================================================

/**
 * 手动绑定表单验证 Schema
 *
 * 用于当自动绑定失败时，用户手动选择案件进行绑定
 */
export const manualBindingSchema = z.object({
  /** 案件 ID - 必填 */
  case_id: z
    .number({ error: '请选择案件' })
    .int('案件ID必须为整数')
    .positive('请选择案件'),

  /** 文书类型 - 可选，允许用户修改识别结果 */
  document_type: z.string().optional(),

  /** 关键时间 - 可选，允许用户修改识别结果 */
  key_time: z.string().optional(),
})

/**
 * 更新识别信息表单验证 Schema
 *
 * 用于修改识别结果（文书类型、关键时间）
 */
export const updateRecognitionInfoSchema = z.object({
  /** 文书类型 - 可选 */
  document_type: z.string().optional(),

  /** 关键时间 - 可选 */
  key_time: z.string().optional(),
})

// ============================================================================
// 文件上传验证
// ============================================================================

/**
 * 文件上传验证工具
 *
 * @validates Requirements 6.2 - 限制上传文件类型为 PDF、图片（jpg/png）
 * @validates Requirements 6.3 - 限制单个文件大小不超过 10MB
 */
export const fileValidation = {
  /**
   * 验证文件类型是否有效
   * @param file - 要验证的文件
   * @returns 文件类型是否在允许列表中
   */
  isValidType: (file: File): boolean =>
    ACCEPTED_FILE_TYPES.includes(file.type as typeof ACCEPTED_FILE_TYPES[number]),

  /**
   * 验证文件大小是否有效
   * @param file - 要验证的文件
   * @returns 文件大小是否在限制范围内
   */
  isValidSize: (file: File): boolean => file.size <= MAX_FILE_SIZE,

  /**
   * 验证文件是否有效（类型和大小都通过）
   * @param file - 要验证的文件
   * @returns 验证结果对象
   */
  validate: (
    file: File
  ): { valid: boolean; error?: string } => {
    if (!fileValidation.isValidType(file)) {
      return {
        valid: false,
        error: '不支持的文件格式，请上传 PDF 或图片文件（jpg/png）',
      }
    }
    if (!fileValidation.isValidSize(file)) {
      return {
        valid: false,
        error: '文件大小超过 10MB 限制',
      }
    }
    return { valid: true }
  },
}

/**
 * 文件上传错误消息
 */
export const FILE_ERRORS = {
  /** 文件类型无效 */
  INVALID_TYPE: '不支持的文件格式，请上传 PDF 或图片文件（jpg/png）',
  /** 文件过大 */
  FILE_TOO_LARGE: '文件大小超过 10MB 限制',
  /** 上传失败 */
  UPLOAD_FAILED: '文件上传失败，请重试',
  /** 网络错误 */
  NETWORK_ERROR: '网络连接失败，请检查网络后重试',
} as const

// ============================================================================
// 类型导出
// ============================================================================

/**
 * 手动绑定表单数据类型
 * 从 Zod Schema 推断
 */
export type ManualBindingFormData = z.infer<typeof manualBindingSchema>

/**
 * 更新识别信息表单数据类型
 * 从 Zod Schema 推断
 */
export type UpdateRecognitionInfoFormData = z.infer<typeof updateRecognitionInfoSchema>
