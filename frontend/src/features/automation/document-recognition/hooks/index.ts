/**
 * Document Recognition Hooks
 * 文书智能识别模块 Hooks 导出
 */

export {
  useRecognitionTasks,
  recognitionTasksQueryKey,
  recognitionTaskQueryKey,
} from './use-recognition-tasks'

export {
  useRecognitionTask,
  shouldPoll,
  isCompleted,
  type UseRecognitionTaskOptions,
} from './use-recognition-task'

export {
  useCaseSearch,
  caseSearchQueryKey,
  type UseCaseSearchOptions,
  type UseCaseSearchResult,
} from './use-case-search'
