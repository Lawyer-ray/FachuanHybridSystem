/**
 * 纯领域逻辑（不可变改 draft）的对外出口。
 * 按职责拆为 resolve / initial / labels / segments / selection / auto-split / info-fields /
 * state / quality / review / engine / md-suspects / detect-parties / party-lookup。
 * 消费方只从这里引（store.ts、components/reader/*），import 路径保持 `../draft` /
 * `../../draft` 不变。
 *
 * 唯一例外：api/inbox-packs.ts 引 ./draft/state 直连子模块——经 barrel 会因
 * resolve → ../api 的既有依赖形成 api ↔ draft 环（state 本身只依赖 types，直连无环）。
 *
 * 只 re-export 当前有外部消费方的符号——barrel 表达的是本域的对外契约，
 * 不是把内部实现摊开。子模块内仍可使用的私有函数不必出现在这里。
 */

export {
  pageRotKey,
  parsePageRotKey,
  normalizeDeg,
  getPageRot,
  rotatedSizeOf,
  rotateRefs,
  setRefsRotation,
  resetRefsRotation,
  countRotated,
  rotateNormRect,
  rotationsForRange,
  firstRotationOf,
  joinRotationEncodings,
} from './page-rotation'
export type { PageRefKey } from './page-rotation'
export { nextSegId, ensureSegIds } from './seg-id'
export { isEmptyDraft, withPageQuality, withEngineDisagreements, withJudgeState, setEngineChecked } from './state'
export {
  readJudgeState,
  mergeJudgeStates,
  judgeGateReasonText,
  judgeGateNotice,
  judgeOutcomeNote,
} from './judge-state'
export { resolveMats, buildInitialDraft } from './resolve'
export {
  matLabel,
  segMats,
  selKeyOf,
  countUnclassified,
  isWholeMat,
  isAutoSegName,
  segRangeText,
  withDefaultNames,
} from './labels'
export {
  splitSegment,
  mergeSegment,
  moveSegment,
  renameSegment,
  resetSegments,
  setPackStatus,
  setPackAssign,
  appendMatsToDraft,
  fillSegmentText,
  setSegmentMarkdown,
  setSegmentBlockText,
  removeSegmentBlock,
} from './segments'
export {
  applyAutoSplit,
  applyAutoSplitPreservingEdits,
  detectAutoSplitConflicts,
  canAutoSplitMat,
  renameMat,
} from './auto-split'
export type { AutoSplitConflict } from './auto-split'
export {
  addInfoField,
  removeInfoField,
  setInfoValue,
  setInfoSource,
} from './info-fields'
export {
  flatRefs,
  pageIndexOf,
  applyPageSelection,
  isSelectionContiguous,
  removePages,
  mergeSegsIntoOne,
} from './selection'
export { blockKeyOf, locateKeyOf } from './block-keys'
export {
  readPageQuality,
  readInconsistencies,
  inconsistencyKindOf,
  sortInconsistencies,
  graphicPagesOf,
  ocrFailedPagesOf,
  sparsePagesOf,
  docHintPagesOf,
  docTypeLabel,
  docTodosOf,
  qualityFlagLabel,
  pagesText,
  reviewHintOf,
} from './quality'
export type { DocTodo, SegmentReviewHint } from './quality'
export {
  readEngineDisagreements,
  readEngineBlocks,
  engineLabel,
  engineShortLabel,
  engineBlocksOfPage,
  disagreementKey,
  uniqueDisagreementKey,
  uniqueDisagreementKeys,
  disagreementKindLabel,
  groupBySeverity,
  sortDisagreements,
  variantTextOf,
  variantFullTextOf,
} from './engine'
export { reviewItemsOf, reviewItemId, sortReviewItems, groupByPage } from './review'
export type { ReviewItem, ReviewItemKind } from './review'
export { diffSegments } from './text-diff'
export { suggestionFor, suggestionsOf } from './engine-suggest'
export type { EngineSuggestion } from './engine-suggest'
export { findSuspects } from './md-suspects'
export type { MdSuspect } from './md-suspects'
export { applyDetectedParties } from './detect-parties'
export { resolveParties } from './party-lookup'
