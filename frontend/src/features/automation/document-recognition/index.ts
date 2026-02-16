/**
 * 文书智能识别模块导出
 * @module document-recognition
 */

// 类型定义
export * from './types'

// 验证 Schema
export * from './schemas'

// API
export { documentRecognitionApi, type PaginatedResponse } from './api'

// Hooks
export {
  useRecognitionTasks,
  useRecognitionTask,
  recognitionTasksQueryKey,
  recognitionTaskQueryKey,
  shouldPoll,
  isCompleted,
  type UseRecognitionTaskOptions,
} from './hooks'

// Mutations
export {
  useUploadDocument,
  useBindCase,
  useUpdateRecognitionInfo,
  type UseUploadDocumentResult,
  type UseBindCaseResult,
  type UseUpdateRecognitionInfoResult,
  type BindCaseParams,
  type UpdateRecognitionInfoParams,
} from './hooks/use-recognition-mutations'

// Components
export {
  FileUploader,
  type FileUploaderProps,
  RecognitionList,
  type RecognitionListProps,
  RecognitionResult,
  type RecognitionResultProps,
  CaseSearchSelect,
  type CaseSearchSelectProps,
  ManualBindingDialog,
  type ManualBindingDialogProps,
  RecognitionDetail,
  type RecognitionDetailProps,
} from './components'
