import { docTodosOf, riskPageKeysOf, segMats } from '../../draft'
import type { DraftState, PageQualityByMi } from '../../types'
import type { DownloadableSegment } from './use-segment-downloads'

/**
 * 左栏目录的**派生数据**：草稿 → 「哪些段可下载 / 待补录几页 / 几页有识别风险 /
 * 段怎么按源文件分组」。
 *
 * 从 `Rail.tsx` 拆出的原因：这些是纯粹的 `DraftState → 视图模型` 换算，
 * 与 `Rail` 真正关心的东西（选中态、改名态、拖拽落点、行交互与布局）没有交集。
 * 混在组件里时，读「拖拽落点怎么判」必须先穿过四段累加循环；改计数口径又得
 * 在一堆 JSX 里找。拆开后同一份换算还能被别处（徽标、测试）直接复用，
 * 不必挂载整个左栏。
 *
 * 口径已由 `Rail.dom.test.tsx` 等锁住，这里只搬位置，不调算法。
 */

/**
 * 可下载的段 = 有后端出处的段（`splitRef` 由自动识别落地时写入）。人工切/合的段
 * 后端没有产物，不进这份清单，也就不出勾选框与下载按钮。
 */
export function downloadablesOf(draft: DraftState): DownloadableSegment[] {
  const { mats } = draft
  return draft.segs.flatMap((sg) => {
    if (!sg.splitRef) return []
    const first = sg.refs[0]
    const last = sg.refs[sg.refs.length - 1]
    if (!first || !last) return []
    // refs 里的 mi 是**素材下标**，页旋转的键用的是附件 partIndex —— 两者在常规
    // 材料包里数值相同，但追加过附件后就会漂；这里按 mats 显式换算。
    const partIndex = mats[first.mi]?.partIndex ?? first.mi
    return [
      { pk: sg.splitRef.pk, jobId: sg.splitRef.jobId, name: sg.fn, partIndex, pageStart: first.p, pageEnd: last.p },
    ]
  })
}

/** 全卷证件待补录页数：入口只在真有这数据时出现（旧任务没有 doc_hints，不渲染假入口） */
export function docTodoCountOf(pageQualityByMi: PageQualityByMi | null): number {
  return docTodosOf(pageQualityByMi).length
}

/**
 * 全卷「识别风险页」计数：退化页与列数突变页取**并集**（同一页两类都命中只算一页，
 * 否则数字大于待核对的页数，律师翻完还差一页）。键是 `${mi}:${p}`——多份 PDF 的
 * 页号各自从 1 开始，只数页号会把「A 的 P3」和「B 的 P3」合并成一页。
 * 只数**当前草稿里还引用着的页**（删掉页后不残留）。旧任务无该键 → 0 → 不渲染。
 *
 * 三个数字一起给：并集 `total` 是徽标，`degenerate` / `column` 分项写进 tooltip
 * 与 aria-label（律师要知道是哪一类，否则只看到一个总数无从下手）。
 */
export function riskPageCountOf(draft: DraftState): { total: number; degenerate: number; column: number } {
  const anomalyByMi = draft.pageAnomalyByMi ?? null
  const degenerateAll = new Set<string>()
  const columnAll = new Set<string>()
  for (const seg of draft.segs) {
    const keys = riskPageKeysOf(seg, anomalyByMi)
    for (const key of keys.degenerate) degenerateAll.add(key)
    for (const key of keys.column) columnAll.add(key)
  }
  return {
    total: new Set([...degenerateAll, ...columnAll]).size,
    degenerate: degenerateAll.size,
    column: columnAll.size,
  }
}

/**
 * 每个素材下挂它的段；跨源段归到「跨源合并」一组。
 *
 * `groups` 的顺序 = 素材在目录里首次出现的顺序（数组按 `mi` 查而不是建 Map），
 * `cross` 保持段序——渲染顺序就是律师看到的顺序，不能用无序容器。
 */
export function groupsOf(draft: DraftState): { groups: { mi: number; segs: number[] }[]; cross: number[] } {
  const groups: { mi: number; segs: number[] }[] = []
  const cross: number[] = []
  draft.segs.forEach((sg, si) => {
    const mis = segMats(sg)
    if (mis.length > 1 || mis.length === 0) {
      cross.push(si)
    } else {
      const g = groups.find((x) => x.mi === mis[0]!)
      if (g) g.segs.push(si)
      else groups.push({ mi: mis[0]!, segs: [si] })
    }
  })
  return { groups, cross }
}
