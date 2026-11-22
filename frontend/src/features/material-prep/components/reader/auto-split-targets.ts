import { canAutoSplitMat } from '../../draft'
import type { BundleMat, DraftState } from '../../types'

/** 一个「素材 + 它在 mats 里的下标」——mi 是所有回写接口的定位键 */
export interface MatTarget {
  mat: BundleMat
  mi: number
}

export interface AutoSplitTargets {
  /** 可以进云端拆分任务的 PDF（人工拆分 / 跨源合并的已被排除） */
  pdf: MatTarget[]
  /**
   * 全部 PDF（含被排除的）。
   *
   * 只用来区分两种「没东西可跑」：全是已拆过的 PDF（该提示「已跳过，可恢复初始分段」）
   * 与压根没有材料（该提示「没有可识别的材料」）。混成一条会让律师以为按钮坏了。
   */
  allPdf: MatTarget[]
  /** 图片：单页取字，不参与分段 */
  photo: MatTarget[]
  /** Word / Excel：走文档解析取字 */
  office: MatTarget[]
}

/**
 * 按附件粒度分派取字路径（见 docs/material-prep-dispatch.md）。
 *
 * 一个材料包里扫描件 / 电子版 / 图片 / Word 混在一起是常态，每类的正确路径不同，
 * 所以**按 mat 逐个选路**，不能按整包一刀切：
 *   · pdf   → 云端拆分任务（后端逐页再选文本层 / 云端 / 本地 OCR）
 *   · photo → 单页取字，图片本就单页，谈不上分段
 *   · office → 文档解析（本地 OOXML），不是 OnlyOffice：DS 是给人看改的编辑器，
 *              抽文本绕远且要再过一遍 OCR
 */
export function autoSplitTargetsOf(draft: DraftState): AutoSplitTargets {
  const all = draft.mats.map((mat, mi) => ({ mat, mi }))
  const allPdf = all.filter(({ mat }) => mat.k === 'pdf')
  return {
    pdf: allPdf.filter(({ mi }) => canAutoSplitMat(draft, mi)),
    allPdf,
    photo: all.filter(({ mat }) => mat.k === 'photo'),
    office: all.filter(({ mat }) => mat.k === 'office'),
  }
}
