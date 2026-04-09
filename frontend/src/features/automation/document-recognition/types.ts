/**
 * 文书智能识别类型定义
 * @module document-recognition/types
 */

// ============================================================================
// 状态枚举
// ============================================================================

/**
 * 识别任务状态
 */
export type RecognitionStatus =
  | 'pending' // 待处理
  | 'processing' // 处理中
  | 'success' // 成功
  | 'failed' // 失败

// ============================================================================
// 实体类型
// ============================================================================

/**
 * 文书识别任务
 */
export interface DocumentRecognitionTask {
  id: number
  /** 文件名 */
  file_name: string
  /** 文件路径 */
  file_path: string
  /** 任务状态 */
  status: RecognitionStatus
  /** 文书类型 */
  document_type: string | null
  /** 案号 */
  case_number: string | null
  /** 关键时间 */
  key_time: string | null
  /** 置信度 */
  confidence: number | null
  /** 提取方法 */
  extraction_method: string | null
  /** 原始文本 */
  raw_text: string | null
  /** 绑定是否成功 */
  binding_success: boolean | null
  /** 绑定的案件 ID */
  case_id: number | null
  /** 绑定的案件名称 */
  case_name: string | null
  /** 绑定的案件日志 ID */
  case_log_id: number | null
  /** 错误信息 */
  error_message: string | null
  /** 创建时间 */
  created_at: string
  /** 更新时间 */
  updated_at: string
}

/**
 * 手动绑定请求
 */
export interface ManualBindingRequest {
  case_id: number
  document_type?: string
  key_time?: string
}

/**
 * 更新识别信息请求
 */
export interface UpdateRecognitionInfoRequest {
  document_type?: string
  key_time?: string
}

/**
 * 案件搜索结果
 */
export interface CaseSearchResult {
  id: number
  name: string
  case_number: string
}

/**
 * 识别任务列表参数
 */
export interface RecognitionListParams {
  page?: number
  page_size?: number
  status?: RecognitionStatus
}
