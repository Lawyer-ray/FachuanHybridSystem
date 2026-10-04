import type { DraftState } from '../types'

/**
 * draft_state 的「空占位」判别（store.open 与 api.setPackStatusRemote 共用）。
 *
 * 后端把从未存过草稿的材料包 draft_state 存为 {}（无任何键），存过草稿则必含
 * segs 键；因此用键存在性判别，而不是 as 强转——消费方拿到的是经运行时验证的
 * 窄化类型。注意「已保存但段被删空」的草稿（segs: [] 仍有 mats/infos）不是空
 * 占位：setPackStatusRemote 回写时必须保留其内容；阅读器打开时是否重建初始
 * 草稿，由 store 在本谓词之上再加 segs.length > 0 判断。
 */
export function isEmptyDraft(ds: DraftState | Record<string, never>): ds is Record<string, never> {
  return !('segs' in ds)
}
