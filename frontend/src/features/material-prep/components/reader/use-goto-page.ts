import { useCallback } from 'react'

import type { EngineDisagreement, Segment } from '../../types'
import { scrollToEngineRects } from './scroll-to-rect'

/**
 * 「页号 → 段 → 页卡 → 滚动」这一套跳转（右栏正文 / 分歧清单 / 质量提示 / 抽屉共用）。
 *
 * 为什么统一到这里：四套跳转原先是 ReaderBody 里四份几乎相同的实现，
 * `document.querySelector('[data-mi][data-p]')` 出现了四次——任何一次改了页卡的
 * 定位属性，另外三处就会静默失效（点了没反应，也没有报错）。
 *
 * 为什么用 data-mi / data-p 查 DOM 而不维护 ref 数组：页数是动态的（切段、追加
 * 材料都会变），维护一份和页数同步的 ref 数组在每次结构变化后都要重建，容易对不上位。
 * 页卡本来就带这两个属性（见 PageCell），查一次 DOM 是最直接的真相来源。
 */
function pageElOf(mi: number, p: number): HTMLElement | null {
  return document.querySelector<HTMLElement>(`[data-mi="${mi}"][data-p="${p}"]`)
}

/** 滚到某页页卡（居中）。找不到就什么都不做——页可能已随段被切掉 */
export function scrollToPage(mi: number, p: number): void {
  pageElOf(mi, p)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
}

/**
 * @param segs          当前草稿的分段（跳转的唯一依据：段的 refs 决定页号映射）
 * @param onFocusSeg    跳转时顺带聚焦该段（中栏只渲染聚焦段的页卡）
 * @param onHighlightBlock   Markdown 侧高亮哪一块（null = 取消高亮）
 * @param onHighlightEngine  页面上高亮哪一条引擎分歧（唯一键；不匹配自然不高亮）
 * @param engineKeys    与 `engineDisagreements` 一一对应的唯一键
 */
export function useGotoPage(params: {
  segs: Segment[]
  onFocusSeg: (si: number) => void
  onHighlightBlock: (key: string | null) => void
  onHighlightEngine: (key: string | null) => void
  engineKeys: string[]
  engineDisagreements: EngineDisagreement[]
}) {
  const { segs, onFocusSeg, onHighlightBlock, onHighlightEngine, engineKeys, engineDisagreements } = params

  /**
   * 质量提示条 / 右栏正文 → 原页：滚到那一段的对应页。
   * 用段做跳转而不是全局页表：段的页卡与律师看到的那一段正文是同一个东西，
   * 跳过去不会让人「知道在第 147 页，却在长列表里找不到」。
   */
  const onGotoSegmentPage = useCallback(
    (si: number, p: number) => {
      const ref = segs[si]?.refs.find((r) => r.p === p)
      if (!ref) return
      onFocusSeg(si)
      scrollToPage(ref.mi, ref.p)
    },
    [segs, onFocusSeg],
  )

  /** 不一致清单 / 证件页清单是**全本视角**，只给了一个页号；按页号找它所在的段再跳 */
  const onGotoAnyPage = useCallback(
    (p: number) => {
      // 多源材料包里同一页码可能出现多次（每份 PDF 都从 1 开始），取第一个能定位到的
      const si = segs.findIndex((s) => s.refs.some((r) => r.p === p))
      if (si < 0) return
      const ref = segs[si]!.refs.find((r) => r.p === p)!
      onFocusSeg(si)
      scrollToPage(ref.mi, ref.p)
    },
    [segs, onFocusSeg],
  )

  /**
   * 右栏 Markdown 的一条 → 滚到原页 + 高亮那个框。
   *
   * 传 null 只清高亮、不滚动（「取消定位」不该把视线又拽走）。
   */
  const onLocateBlock = useCallback(
    (key: string | null) => {
      onHighlightBlock(key)
      if (!key) return
      // key 形如 `<segId>:<page>:<idx>`：只用到段内页序来定位，页号在第 2 段
      const seg = segs.find((s) => key.startsWith(`${s.id}:`))
      if (!seg) return
      const pageNo = Number(key.split(':')[1])
      // 按页号 find，不能用 `page_no - firstPage` 当下标：切出几页 / 删页之后
      // refs 可以是 [1, 3, 7] 这种跳号序列，减法会错位到别的页上。
      const ref = seg.refs.find((r) => r.p === pageNo)
      if (!ref) return
      scrollToPage(ref.mi, ref.p)
    },
    [segs, onHighlightBlock],
  )

  /**
   * 点一条引擎分歧：滚到那一页 + 记住高亮（Flow 据此在该页画两个引擎的框）。
   *
   * 抽屉**不关**：律师要一边看清单一边对原件，关掉就得多点一次再打开。
   */
  const onJumpEngineDisagreement = useCallback(
    (pageNo: number, key: string) => {
      // ⚠ 必须用抽屉传下来的**唯一键**，既不能按页号 `find`、也不能用下标。
      //
      // 旧实现是 `engineDisagreements.find(d => d.page_no === pageNo)`：一页只有
      // 一条分歧时看不出问题，但一页有多条时永远命中第一条。拿真实 164 页卷宗
      // 的 332 条分歧统计：127 个有分歧的页里 74 页是 2 条以上，共 279 条（84%）
      // 无法被单独定位——点第 34 条和第 1 条效果一样，律师看到的就是「点了没反应」。
      //
      // 也不能用下标：分组会按严重度重排，组内下标与这里的全局下标不是一回事。
      // 键是内容派生的，不受排序影响。
      onHighlightEngine(key)
      onGotoAnyPage(pageNo)

      // 再滚到**框的位置**（不只是页顶）：一页上千像素高，只到页顶等于没定位。
      // 没有块坐标时（约 11%）该函数直接返回，保持「只跳页」不伪造精度。
      const item = engineDisagreements.find((_, i) => engineKeys[i] === key)
      const si = segs.findIndex((sg) => sg.refs.some((r) => r.p === pageNo))
      if (si < 0) return
      const ref = segs[si]!.refs.find((r) => r.p === pageNo)
      if (!ref) return
      scrollToEngineRects(ref.mi, ref.p, item?.blocks ?? [])
    },
    [onGotoAnyPage, onHighlightEngine, engineDisagreements, engineKeys, segs],
  )

  return { onGotoSegmentPage, onGotoAnyPage, onLocateBlock, onJumpEngineDisagreement }
}
