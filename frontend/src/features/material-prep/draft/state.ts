import type { DraftState, EngineDisagreement, PageQuality } from '../types'

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

/**
 * 把后端 `summary.page_quality` 落到草稿上（只用于展示，**故意不进持久化**）。
 *
 * 为什么不进持久化：质量统计是「这次识别产出了什么」的附带事实，落盘后会和
 * 律师那之后的切段 / 合段 / 删页错位（段可能早已不是识别时那几页了），刷新一次
 * 就变成一句与现状不符的假提示。它本来就随那次识别结果一起回来，重新打开材料包
 * 时再带上即可。因此 `draft-persistence` 与 `api` 用 `DraftStateToSave` 剔除该字段。
 *
 * 空/缺失不写入：旧任务的 summary 里没这个键，写成 `{"graphic_pages": [], …}`
 * 只会让「有没有质量数据」这件事故意模糊。
 */
export function withPageQuality(d: DraftState, quality: PageQuality | null): DraftState {
  return quality ? { ...d, pageQuality: quality } : d
}

/**
 * 把双引擎分歧清单落到草稿上；空清单不写入（旧任务 / 单引擎路径的 summary 里没这个键，
 * 写成 `[]` 只会让「有没有跑过双引擎」这件事故意模糊）。
 *
 * 重跑时**清掉旧的已核对记录**：分歧是按内容做键的（`disagreementKey`），新一次识别
 * 的结果与上一次并非同一批条目，留着旧勾会让律师以为这处已经看过了。
 */
export function withEngineDisagreements(
  d: DraftState,
  disagreements: EngineDisagreement[],
): DraftState {
  if (disagreements.length === 0) {
    // 没有新分歧时也不硬塞空数组；但旧的分歧/核对记录必须清掉（它们描述的是上一次识别）
    if (d.engineDisagreements === undefined && d.engineChecked === undefined) return d
    const { engineDisagreements: _drop, engineChecked: _dropChecked, ...rest } = d
    return rest
  }
  return { ...d, engineDisagreements: disagreements, engineChecked: [] }
}

/**
 * 勾选 / 取消「已核对」。
 *
 * 只改草稿不动 UI state：核对结论要跨刷新保留（见 `DraftState.engineChecked` 的说明），
 * 而草稿本身走防抖保存，勾一下就是一次普通编辑。
 */
export function setEngineChecked(d: DraftState, key: string, checked: boolean): DraftState {
  const cur = d.engineChecked ?? []
  const has = cur.includes(key)
  if (checked === has) return d
  return { ...d, engineChecked: checked ? [...cur, key] : cur.filter((k) => k !== key) }
}
