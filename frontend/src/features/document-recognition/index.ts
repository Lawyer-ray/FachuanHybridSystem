/** 文书识别域出口：组件 / Hook / 领域类型。 */

export { RecognizeDialog } from './components/RecognizeDialog'
export { useRecognize } from './hooks/use-recognize'
export {
  fileRejectReason,
  rowsFromParsed,
  rowsFromTask,
  toLocalInputValue,
  type CandidateRow,
  type ParsedCandidate,
} from './domain'
export { ACCEPT_EXTENSIONS, MAX_FILE_MB } from './constants'
export type { TaskOut, DateCandidate, CaseRecommendation, CaseSearchItem } from './types'
