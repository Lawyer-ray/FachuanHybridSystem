/**
 * 纯领域逻辑（不可变改 draft）的对外出口。
 * 按职责拆为 resolve / labels / segments / selection / auto-split / info-fields，
 * 消费方只从这里引（store.ts、reader/*），import 路径保持 `../draft` / `../../draft` 不变。
 */

export { resolveMats, effectiveFileName, initialSegments, buildInitialDraft } from './resolve'
export {
  matLabel,
  segMats,
  isCross,
  pageLabel,
  segColorOf,
  selKeyOf,
  pageKeyOf,
  rangeLabel,
  countUnclassified,
  isAllClassified,
  totalPagesOfMats,
  isWholeMat,
} from './labels'
export {
  splitSegment,
  mergeSegment,
  setSegmentType,
  renameSegment,
  resetSegments,
  setPackStatus,
  setPackAssign,
  appendMatsToDraft,
} from './segments'
export {
  applyAutoSplit,
  canAutoSplitMat,
  renameMat,
} from './auto-split'
export {
  addInfoField,
  removeInfoField,
  setInfoValue,
  setInfoSource,
} from './info-fields'
export {
  flatRefs,
  pageIndexOf,
  splitOutPages,
  mergePagesIntoNew,
  applyPageSelection,
  isSelectionContiguous,
  removePages,
  type FlatRef,
} from './selection'
