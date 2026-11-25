import { countRotated } from '../../draft'
import type { DraftState, PageKey } from '../../types'

/**
 * 「转正」按钮作用在哪些页。
 *
 * ## 为什么要有优先级，而不是固定作用于选中页
 *
 * 真实场景里律师的第一反应是「这一整份都倒了」（倒着送纸扫出来的 37 页全都歪），
 * 此时他不会先去勾 37 个页再转身；而另一种场景是「只有第 5 页放反了」，那时
 * 勾一页再转才是对的。两级都能覆盖，优先级取**意图最强的那一个**：
 *
 * 1. 有选中页 → 只转选中的（明确的逐页意图）；
 * 2. 没选中 → 转**当前段**（左栏点中的那一段 / 默认第一段）：这正是「这一份材料」
 *    的粒度，点击成本为零；
 * 3. 连段都没有（草稿里还没分段）→ 全部页。
 *
 * 标签必须把这个落点写出来（「所选 12 页」/「当前段 37 页」/「全部 37 页」）：
 * 一个不写目标范围的批量按钮，律师不敢按——转错 37 页的代价是再转回去。
 */
export interface RotationTarget {
  /** 要改的页（`mi` + 页号，与 store 的 rotatePages 同口径） */
  refs: PageKey[]
  /** 给人看的目标描述，直接进按钮 title 与菜单标题 */
  label: string
  /** 目标里已经转过正的有几页（0 时「重置方向」置灰） */
  rotatedCount: number
}

export function rotationTargetOf(
  draft: DraftState | null,
  selPages: readonly PageKey[],
  focusedSeg: number,
): RotationTarget {
  if (!draft) return { refs: [], label: '没有可转的页', rotatedCount: 0 }

  let refs: PageKey[]
  let label: string
  if (selPages.length > 0) {
    refs = [...selPages]
    label = `所选 ${refs.length} 页`
  } else {
    const seg = draft.segs[focusedSeg]
    if (seg && seg.refs.length > 0) {
      refs = [...seg.refs]
      label = `当前段 ${refs.length} 页`
    } else {
      refs = allPageRefs(draft)
      label = `全部 ${refs.length} 页`
    }
  }
  return { refs, label, rotatedCount: countRotatedFor(draft, refs) }
}

/** 把 `mi:page` 换成旋转表的键（`partIndex:page`）后数已转正的页数 */
function countRotatedFor(draft: DraftState, refs: readonly PageKey[]): number {
  const keys = refs.flatMap((ref) => {
    const mat = draft.mats[ref.mi]
    return mat ? [{ partIndex: mat.partIndex, page: ref.p }] : []
  })
  return countRotated(draft.pageRot, keys)
}

function allPageRefs(draft: DraftState): PageKey[] {
  const refs: PageKey[] = []
  draft.mats.forEach((mat, mi) => {
    for (let p = 1; p <= mat.pages; p += 1) refs.push({ mi, p })
  })
  return refs
}
