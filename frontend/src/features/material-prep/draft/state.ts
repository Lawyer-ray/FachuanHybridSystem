import type { DraftState, EngineDisagreement, JudgeState, PageAnomaly, PageQuality } from '../types'

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
 * 把某一**份** PDF 的页级质量落到草稿上（按 `mi` 分槽，见 `PageQualityByMi`；**随草稿持久化**）。
 *
 * 曾经故意不落盘，理由是「质量统计是这次识别的附带事实，落盘后会和律师之后的
 * 切段/合段/删页错位」。那个担心代码里已经天然解决：`graphicPagesOf` /
 * `docHintPagesOf` 都是拿 `seg.refs` 逐条查对应源再求交集，段变了提示跟着变。
 * 而不落盘的代价很实在——刷新一次提示就没了，律师得重新点「自动识别」才看得到。
 * 持久化口径见 `DraftStateToSave`（已是完整 DraftState 形状）。
 *
 * 按源存而不是整份覆盖（与 `withPageAnomaly` 同形）：一个包可以有多份 PDF，页号各自
 * 从 1 开始。整份覆盖会 ① 只留下最后一份（丢页）② 让「A 份的 P5 取字失败」显示到
 * B 份的 P5 段上（给错页）。
 *
 * 空/缺失不写入：旧任务的 summary 里没这个键，写成 `{"graphic_pages": [], …}`
 * 只会让「有没有质量数据」这件事故意模糊。`null` = 这一份本次没有信号，**只删该槽**；
 * 最后一槽清空时整个键消失（回到「与引入前逐位一致」）。
 */
export function withPageQuality(d: DraftState, mi: number, quality: PageQuality | null): DraftState {
  const key = String(mi)
  const current = d.pageQualityByMi
  if (!quality) {
    if (!current || !(key in current)) return d
    const { [key]: _drop, ...rest } = current
    if (Object.keys(rest).length === 0) {
      const { pageQualityByMi: _dropAll, ...without } = d
      return without
    }
    return { ...d, pageQualityByMi: rest }
  }
  return { ...d, pageQualityByMi: { ...(current ?? {}), [key]: quality } }
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
 * 把「分歧裁定这次判了没有」落到草稿上。
 *
 * 与 `engineDisagreements` 同级同生命周期：它们本是同一份识别的两面（一边是分歧条目，
 * 一边是「这些条目到底有没有被自动判过」）。**必须持久化**：律师问「为什么全是人工」
 * 的时机往往是第二天重新打开这个包，那时 summary 早就不在内存里了。
 *
 * `null`（旧任务）不写入，且**清掉旧值**：重跑一次没带这个键时，留着上一次的
 * 「未生效」提示会变成假信息——它描述的是上一次识别。
 */
export function withJudgeState(d: DraftState, state: JudgeState | null): DraftState {
  if (!state) {
    if (d.judgeState === undefined) return d
    const { judgeState: _drop, ...rest } = d
    return rest
  }
  return { ...d, judgeState: state }
}

/**
 * 把某一**份** PDF 的页级风险落进草稿（按 `mi` 分槽，见 `PageAnomalyByMi`）。
 *
 * 按源存而不是整份覆盖：一个包可以有多份 PDF，页号各自从 1 开始。整份覆盖会
 * ① 只留下最后一份（丢页）② 让「A 份的 P5 退化」显示到 B 份的 P5 段上（给错页）。
 *
 * `null` = 这一份本次没有信号（旧任务 / 没跑到表格几何）：**删掉该源那一槽**，
 * 留上一次的结果是假信息；所有槽都空了就把整个键去掉，回到「与引入前逐位一致」。
 */
export function withPageAnomaly(d: DraftState, mi: number, anomaly: PageAnomaly | null): DraftState {
  const key = String(mi)
  const current = d.pageAnomalyByMi
  if (!anomaly) {
    if (!current || !(key in current)) return d
    const { [key]: _drop, ...rest } = current
    if (Object.keys(rest).length === 0) {
      const { pageAnomalyByMi: _dropAll, ...without } = d
      return without
    }
    return { ...d, pageAnomalyByMi: rest }
  }
  return { ...d, pageAnomalyByMi: { ...(current ?? {}), [key]: anomaly } }
}

/**
 * 兼容**存量草稿**的单值 `pageQuality`（v27.26.2 起改成按源存）。
 *
 * 不做这一步的后果很具体：律师已经存过草稿的包，打开后图纸页 / 取字失败页的提示
 * 会**全部消失**，直到他重跑一次识别。这不是新功能该有的代价。
 *
 * 归属规则（只在不猜的前提下迁移）：
 * - 草稿只引用**一个**源（`refs[].mi` 只有一个取值）→ 单值必然是它的，直接归到该源；
 * - 一段都没引用（空草稿）→ 归到 `0`（单源包就是 0）；
 * - 引用了**多个**源 → 无法判断这份单值属于谁，**丢弃**（错配到别的源上比不显示更糟）。
 *
 * 迁移是只读兼容：读到即转换，下一次保存自然写成新形状；旧的单值键一律删掉，
 * 避免它永远躺在草稿里与新键并存。
 */
export function adoptLegacyPageQuality(d: DraftState): DraftState {
  const raw = d as DraftState & { pageQuality?: PageQuality | null }
  const legacy = raw.pageQuality ?? null
  if (!legacy) return d
  const { pageQuality: _drop, ...rest } = raw
  if (rest.pageQualityByMi) return rest

  const sources = new Set<number>()
  for (const seg of rest.segs) {
    for (const ref of seg.refs) sources.add(ref.mi)
  }
  if (sources.size > 1) return rest
  const mi = sources.size === 1 ? [...sources][0]! : 0
  return { ...rest, pageQualityByMi: { [String(mi)]: legacy } }
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
