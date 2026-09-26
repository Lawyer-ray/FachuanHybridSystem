import {
  flatRefs,
  pageIndexOf,
  mergeSegment as segMerge,
  renameSegment as segRename,
  setSegmentType as segSetType,
  splitSegment as segSplit,
  addInfoField as infoAdd,
  removeInfoField as infoRemove,
  setInfoValue as infoSetValue,
} from '../../draft'
import type { DraftState, InfoField, PageKey } from '../../types'

/** Flow onOp 的形状（与 Flow.tsx 的 props 类型保持一致） */
export interface FlowOps {
  setSegType: (si: number, t: string) => void
  renameSeg: (si: number, name: string) => void
  mergeSeg: (si: number) => void
  toggleDone: (si: number) => void
  splitSeg: (si: number, k: number) => void
  pickPage: (mi: number, p: number) => void
}

/** MetaPanel ops 的形状 */
export interface MetaOps {
  addInfo: (field: InfoField) => void
  removeInfo: (di: number) => void
  setValue: (di: number, v: string) => void
}

type Update = (fn: (d: DraftState) => DraftState) => void

/**
 * Reader 的「draft 不可变操作 → store.update」接线。
 * 把散落在 JSX 里的对象字面量收成纯工厂，Reader 只调用一次，ops 形状也可被单测。
 */

export function buildFlowOps(
  update: Update,
  pickPage: (mi: number, p: number) => void,
): FlowOps {
  return {
    setSegType: (si, t) => update((d) => segSetType(d, si, t)),
    renameSeg: (si, name) => update((d) => segRename(d, si, name)),
    mergeSeg: (si) => update((d) => segMerge(d, si)),
    toggleDone: (si) =>
      update((d) => ({ ...d, segs: d.segs.map((s, i) => (i === si ? { ...s, done: !s.done } : s)) })),
    splitSeg: (si, k) => update((d) => segSplit(d, si, k)),
    pickPage,
  }
}

export function buildMetaOps(update: Update): MetaOps {
  return {
    addInfo: (field) => update((d) => infoAdd(d, field)),
    removeInfo: (di) => update((d) => infoRemove(d, di)),
    setValue: (di, v) => update((d) => infoSetValue(d, di, v)),
  }
}

/** 选中页汇总：条数 + 是否跨段（供 SelectionBar 展示） */
export function selDetailOf(draft: DraftState, selPages: PageKey[]) {
  const idx = selPages.map((o) => pageIndexOf(draft, o.mi, o.p)).filter((i) => i >= 0)
  const flat = flatRefs(draft)
  const involved = new Set(idx.map((i) => flat[i]?.si))
  return { count: selPages.length, cross: involved.size > 1 }
}
