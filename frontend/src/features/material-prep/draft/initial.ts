import type { BundleMat, PageKey, Segment } from '../types'
import { nextSegId } from './seg-id'

/**
 * 初始草稿里**不含副作用**的那一段：每个源素材默认一整段，覆盖其全部页。
 *
 * 为什么单独成文件：这段逻辑的两个消费方是 `resolve.buildInitialDraft`（读附件
 * 字节算页数，所以本目录唯一含副作用的就是 resolve）与 `segments.resetSegments`
 * （纯不可变运算）。留在 resolve 里会让纯运算层反向依赖含副作用层——`segments`
 * 只要一份「每源一段」的初始化，却被迫把 `../api` 与 pdf.js 一起拉进模块图。
 */
export function initialSegments(mats: BundleMat[]): Segment[] {
  return mats.map((m, mi) => {
    const refs: PageKey[] = []
    for (let p = 1; p <= m.pages; p++) refs.push({ mi, p })
    return { id: nextSegId(), t: '', fn: m.n, refs, manual: false }
  })
}
