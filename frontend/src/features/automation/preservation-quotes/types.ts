/**
 * 财产保全询价类型定义
 * @module preservation-quotes/types
 */

// ============================================================================
// 状态枚举
// ============================================================================

/**
 * 询价任务状态
 */
export type QuoteStatus =
  | 'pending' // 待执行
  | 'running' // 执行中
  | 'success' // 成功
  | 'partial_success' // 部分成功
  | 'failed' // 失败

/**
 * 保险报价状态
 */
export type InsuranceQuoteStatus = 'success' | 'failed'

// ============================================================================
// 实体类型
// ============================================================================

/**
 * 财产保全询价任务
 */
export interface PreservationQuote {
  id: number
  /** 保全金额 */
  preserve_amount: string
  /** 企业 ID */
  corp_id: string
  /** 类别 ID */
  category_id: string
  /** 凭证 ID */
  credential_id: number
  /** 任务状态 */
  status: QuoteStatus
  /** 总公司数 */
  total_companies: number
  /** 成功数 */
  success_count: number
  /** 失败数 */
  failed_count: number
  /** 错误信息 */
  error_message: string | null
  /** 创建时间 */
  created_at: string
  /** 开始时间 */
  started_at: string | null
  /** 完成时间 */
  finished_at: string | null
  /** 保险报价列表 */
  quotes: InsuranceQuote[]
}

/**
 * 保险公司报价
 */
export interface InsuranceQuote {
  id: number
  /** 公司 ID */
  company_id: string
  /** 公司代码 */
  company_code: string
  /** 公司名称 */
  company_name: string
  /** 保费 */
  premium: string | null
  /** 最低保费 */
  min_premium: string | null
  /** 最低金额 */
  min_amount: string | null
  /** 最高金额 */
  max_amount: string | null
  /** 最低费率 */
  min_rate: string | null
  /** 最高费率 */
  max_rate: string | null
  /** 状态 */
  status: InsuranceQuoteStatus
  /** 错误信息 */
  error_message: string | null
}

/**
 * 创建询价请求
 */
export interface PreservationQuoteCreate {
  preserve_amount: number
  corp_id: string
  category_id: string
  credential_id: number
}

// ============================================================================
// 列表响应
// ============================================================================

/**
 * 分页响应
 */
export interface PaginatedResponse<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}

/**
 * 列表查询参数
 */
export interface QuoteListParams {
  page?: number
  page_size?: number
  status?: QuoteStatus
}
