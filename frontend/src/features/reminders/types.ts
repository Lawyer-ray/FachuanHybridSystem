/**
 * Reminder Types and Interfaces
 * 重要日期提醒类型定义
 *
 * @module features/reminders/types
 */

// ============================================================================
// 提醒类型枚举
// ============================================================================

/**
 * 提醒类型
 * - hearing: 开庭
 * - asset_preservation_expires: 财产保全到期日
 * - evidence_deadline: 举证到期日
 * - appeal_deadline: 上诉期到期日
 * - statute_limitations: 诉讼时效到期日
 * - payment_deadline: 缴费期限
 * - submission_deadline: 补正/材料提交期限
 * - other: 其他
 */
export type ReminderType =
  | 'hearing'
  | 'asset_preservation_expires'
  | 'evidence_deadline'
  | 'appeal_deadline'
  | 'statute_limitations'
  | 'payment_deadline'
  | 'submission_deadline'
  | 'other'

/**
 * 提醒类型标签映射
 * 用于将类型值转换为中文显示标签
 */
export const REMINDER_TYPE_LABELS: Record<ReminderType, string> = {
  hearing: '开庭',
  asset_preservation_expires: '财产保全到期日',
  evidence_deadline: '举证到期日',
  appeal_deadline: '上诉期到期日',
  statute_limitations: '诉讼时效到期日',
  payment_deadline: '缴费期限',
  submission_deadline: '补正/材料提交期限',
  other: '其他',
}

// ============================================================================
// 提醒状态（前端计算）
// ============================================================================

/**
 * 提醒状态
 * - overdue: 已逾期（due_at 已过期）
 * - upcoming: 即将到期（7天内到期）
 * - normal: 正常（超过7天）
 */
export type ReminderStatus = 'overdue' | 'upcoming' | 'normal'

// ============================================================================
// 提醒实体
// ============================================================================

/**
 * 提醒实体（API 响应）
 */
export interface Reminder {
  /** 提醒 ID */
  id: number
  /** 关联合同 ID */
  contract: number | null
  /** 关联案件日志 ID */
  case_log: number | null
  /** 提醒类型 */
  reminder_type: ReminderType
  /** 提醒类型标签（后端返回） */
  reminder_type_label: string
  /** 提醒内容 */
  content: string
  /** 到期时间（ISO datetime） */
  due_at: string | null
  /** 元数据 */
  metadata: Record<string, unknown>
  /** 创建时间（ISO datetime） */
  created_at: string | null
}

/**
 * 提醒输入（创建/更新）
 */
export interface ReminderInput {
  /** 关联合同 ID（与 case_log_id 二选一） */
  contract_id?: number | null
  /** 关联案件日志 ID（与 contract_id 二选一） */
  case_log_id?: number | null
  /** 提醒类型 */
  reminder_type: ReminderType
  /** 提醒内容 */
  content: string
  /** 到期时间（ISO datetime） */
  due_at: string
  /** 元数据 */
  metadata?: Record<string, unknown>
}

// ============================================================================
// 提醒类型选项
// ============================================================================

/**
 * 提醒类型选项（用于下拉选择）
 */
export interface ReminderTypeOption {
  /** 类型值 */
  value: ReminderType
  /** 显示标签 */
  label: string
}

// ============================================================================
// 筛选条件
// ============================================================================

/**
 * 提醒筛选条件
 */
export interface ReminderFilters {
  /** 按提醒类型筛选 */
  reminderType?: ReminderType
  /** 日期范围起始 */
  dateFrom?: Date
  /** 日期范围结束 */
  dateTo?: Date
}
