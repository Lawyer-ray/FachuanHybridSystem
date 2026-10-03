import type { DraftState } from '../types'

/**
 * 段稳定 id：所有创建 Segment 的地方都从这里取。
 * 阅读器列表 key 必须用稳定 id——split/merge/删页后段会增删移位，
 * 拿数组下标当 key 会把组件内部状态错绑到别的段上。
 */
let segSeq = 0

export function nextSegId(): string {
  return `seg-${++segSeq}`
}

/** 存量草稿兼容：老 draft_state 里的段没有 id，读取时兜底补齐 */
export function ensureSegIds(d: DraftState): DraftState {
  if (d.segs.every((sg) => sg.id)) return d
  return { ...d, segs: d.segs.map((sg) => (sg.id ? sg : { ...sg, id: nextSegId() })) }
}
