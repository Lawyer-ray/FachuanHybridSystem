/**
 * 自动化工具模块统一导出
 * @module automation
 */

// 共享常量
export * from './constants'

// 财产保全询价子模块 - 使用命名空间导出避免冲突
export * as preservationQuotes from './preservation-quotes'

// 文书智能识别子模块 - 使用命名空间导出避免冲突
export * as documentRecognition from './document-recognition'

// 直接导出常用的 API 和 Hooks（重命名避免冲突）
// Preservation Quotes
export { preservationQuoteApi } from './preservation-quotes'
export {
  useQuotes,
  useQuote,
  quotesQueryKey,
  quoteQueryKey,
  useCreateQuote,
  useExecuteQuote,
  useRetryQuote,
} from './preservation-quotes'
export { quoteCreateSchema } from './preservation-quotes'

// Document Recognition
export { documentRecognitionApi } from './document-recognition'
export {
  useRecognitionTasks,
  useRecognitionTask,
  recognitionTasksQueryKey,
  recognitionTaskQueryKey,
} from './document-recognition'
export { manualBindingSchema, fileValidation } from './document-recognition'
