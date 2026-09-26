/**
 * 纯领域逻辑（不可变改 draft）的对外出口。
 * 按职责拆为 resolve / labels / segments / selection / auto-split / info-fields，
 * 消费方只从这里引（store.ts、reader/*），import 路径保持 `../draft` / `../../draft` 不变。
 *
 * 只 re-export 当前有外部消费方的符号——barrel 表达的是本域的对外契约，
 * 不是把内部实现摊开。子模块内仍可使用的私有函数不必出现在这里。
 */

export { resolveMats, initialSegments, buildInitialDraft } from './resolve'
export {
  matLabel,
  segMats,
  selKeyOf,
  rangeLabel,
  countUnclassified,
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
  applyPageSelection,
  isSelectionContiguous,
  removePages,
  type FlatRef,
} from './selection'
