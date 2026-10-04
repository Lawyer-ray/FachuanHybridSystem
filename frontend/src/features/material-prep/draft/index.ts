/**
 * 纯领域逻辑（不可变改 draft）的对外出口。
 * 按职责拆为 resolve / labels / segments / selection / auto-split / info-fields / state，
 * 消费方只从这里引（store.ts、reader/*），import 路径保持 `../draft` / `../../draft` 不变。
 * 例外：api.ts 引 ./draft/state 直连子模块——经 barrel 会因 resolve → ../api 的
 * 既有依赖形成 api ↔ draft 环（state 本身只依赖 types，直连无环）。
 *
 * 只 re-export 当前有外部消费方的符号——barrel 表达的是本域的对外契约，
 * 不是把内部实现摊开。子模块内仍可使用的私有函数不必出现在这里。
 */

export { nextSegId, ensureSegIds } from './seg-id'
export { isEmptyDraft } from './state'
export { resolveMats, buildInitialDraft } from './resolve'
export {
  matLabel,
  segMats,
  selKeyOf,
  countUnclassified,
  isWholeMat,
} from './labels'
export {
  splitSegment,
  mergeSegment,
  setSegmentType,
  renameSegment,
  resetSegments,
  toggleSegDone,
  markAllSegsDone,
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
} from './selection'
