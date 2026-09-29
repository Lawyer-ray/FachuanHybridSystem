/**
 * 文书识别域出口：组件 / 领域类型。
 *
 * RecognizeDialog 走 lazy 出口：home 首屏卡片（SideCards）静态引用本模块取
 * domain 纯函数，若在这里静态 re-export 弹窗组件，dynamic import 会被静态
 * 依赖钉死拆不出 chunk（INEFFECTIVE_DYNAMIC_IMPORT），首屏被迫背上整个识别
 * 弹窗 UI。useRecognize 无外部消费方，随弹窗进懒 chunk，不再对外暴露。
 */

import { lazy } from 'react'

/** 文书识别弹窗（懒加载组件，消费方需包 Suspense） */
export const RecognizeDialogLazy = lazy(() =>
  import('./components/RecognizeDialog').then((m) => ({ default: m.RecognizeDialog })),
)

/** 预热识别弹窗 chunk：在触发弹窗前的用户操作（选文件 / 文字解析）期间并行下载 */
export function preloadRecognizeDialog(): void {
  void import('./components/RecognizeDialog')
}

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
