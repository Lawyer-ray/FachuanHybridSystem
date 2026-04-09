/**
 * 自动化工具模块共享常量
 * @module automation/constants
 */

/**
 * 轮询间隔配置（毫秒）
 */
export const POLLING_INTERVALS = {
  /** 询价执行中轮询间隔：3秒 */
  QUOTE_RUNNING: 3000,
  /** 识别处理中轮询间隔：2秒 */
  RECOGNITION_PROCESSING: 2000,
  /** 轮询超时时间：5分钟 */
  POLLING_TIMEOUT: 5 * 60 * 1000,
} as const

/**
 * 文件上传配置
 */
export const FILE_UPLOAD = {
  /** 允许的文件类型 */
  ACCEPTED_FILE_TYPES: ['application/pdf', 'image/jpeg', 'image/png'] as const,
  /** 最大文件大小：10MB */
  MAX_FILE_SIZE: 10 * 1024 * 1024,
} as const

/**
 * 便捷导出
 */
export const ACCEPTED_FILE_TYPES = FILE_UPLOAD.ACCEPTED_FILE_TYPES
export const MAX_FILE_SIZE = FILE_UPLOAD.MAX_FILE_SIZE
