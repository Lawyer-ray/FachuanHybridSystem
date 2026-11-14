import { useCallback, useState } from 'react'

import type { DraftState, OcrPending, PageKey } from '../../types'
import type { useReaderOcr } from './use-ocr'
import { Flow } from './Flow'
import { HintBar } from './HintBar'
import { MetaPanel } from './MetaPanel'
import { Rail } from './Rail'
import { SelectionBar } from './SelectionBar'
import type { buildFlowOps, buildMetaOps } from './reader-ops'

/**
 * 阅读器三栏主体 + 取字/选页提示条 + 选页汇总条。
 *
 * 从 Reader 抽出来的原因很单纯：这一段是"纯 JSX 装配"（没有任何状态与派生），
 * 却是 Reader 里最长的部分，把它留在顶层编排里，topbar / dialogs / 抽屉的
 * 接线就被挤到看不见。这里只收 props，谁提供数据由 Reader 决定。
 */
export function ReaderBody({
  draft,
  messageId,
  narrow,
  railOpen,
  metaOpen,
  onCollapsePanels,
  railWrapCls,
  metaWrapCls,
  pickInfo,
  pickField,
  selMode,
  selPages,
  selCount,
  selCross,
  focusedSeg,
  zoom,
  effCols,
  ocrPending,
  flowOps,
  metaOps,
  onToggleSel,
  onOcrBox,
  onRequestDelete,
  onFocusSeg,
  onRenameMat,
  onSetPickInfo,
  onClearSel,
  onApplySel,
  onExitHint,
  flowWrapRef,
}: {
  draft: DraftState
  messageId: number
  narrow: boolean
  railOpen: boolean
  metaOpen: boolean
  onCollapsePanels: () => void
  railWrapCls: string
  metaWrapCls: string
  pickInfo: number
  pickField: string
  selMode: boolean
  selPages: PageKey[]
  selCount: number
  selCross: boolean
  focusedSeg: number
  zoom: number
  effCols: number
  ocrPending: OcrPending | null
  flowOps: ReturnType<typeof buildFlowOps>
  metaOps: ReturnType<typeof buildMetaOps>
  onToggleSel: (mi: number, p: number, shift: boolean) => void
  onOcrBox: ReturnType<typeof useReaderOcr>['onOcrBox']
  onRequestDelete: (picked: PageKey[]) => void
  onFocusSeg: (si: number) => void
  onRenameMat: (mi: number) => void
  onSetPickInfo: (i: number) => void
  onClearSel: () => void
  onApplySel: () => void
  onExitHint: () => void
  /** 中栏滚动容器的 ref：滚轮缩放要用它算锚点（scrollTop/scrollHeight），
   *  宽度测量也挂在它上面。此前这个 ref 在 hook 里创建却**从未挂到 DOM**，
   *  中栏也就没有任何 overflow —— 表现是「永远停在第一页，滚不动」。 */
  flowWrapRef: (node: HTMLDivElement | null) => void
}) {
  // Markdown 面板展开态：右栏自己记，不落草稿（纯阅读偏好）
  const [mdOpen, setMdOpen] = useState(true)
  // 当前高亮的定位块；null = 不预先高亮任何框（一进阅读器满屏重点反而看不出对应关系）
  const [focusedBlockKey, setFocusedBlockKey] = useState<string | null>(null)
  /**
   * 「要求 Markdown 面板对这块进入修改态」的一次性信号。
   *
   * 为何不能复用 focusedBlockKey：那个既有值也表示「从 Markdown 侧选中了某块」
   * （那时不该自动弹输入框）。只有「从页面框双击过来」这一条路径要进编辑，
   * 所以用一个独立的 key 表达意图，Markdown 侧消费后自行清空。
   */
  const [editRequestKey, setEditRequestKey] = useState<string | null>(null)

  /**
   * 双击 Markdown 的一条 → 滚到原页 + 高亮那个框。
   *
   * 用 data-mi / data-p 找页卡而不用 ref 数组：页数是动态的（切段、追加材料都会变），
   * 维护一份和页数同步的 ref 数组在每次结构变化后都要重建，容易对不上位。
   * 页卡本来就带这两个属性（PageCell 上），查一次 DOM 是最直接的真相来源。
   *
   * 传 null 只清高亮、不滚动（「取消定位」不该把视线又拽走）。
   */
  /**
   * 双击页面上的定位框 → 高亮 Markdown 对应那条并进入修改态。
   *
   * 与 `onLocateBlock` 是**反向**的两条路：
   *   · onLocateBlock：Markdown → 页面（滚到原页 + 框加亮）
   *   · onActivateHit ：页面 → Markdown（高亮那条 + 直接可改）
   * 律师的直觉是「我在原件上看到这行不对，点它就该能就地改」，
   * 所以这条要走编辑态，而不是只加个高亮。
   */
  const onActivateHit = useCallback((key: string) => {
    setFocusedBlockKey(key)
    setEditRequestKey(key)
    // 右栏若被折叠，展开它——否则「高亮了但看不见」
    setMdOpen(true)
  }, [])

  const onLocateBlock = useCallback((key: string | null) => {
    setFocusedBlockKey(key)
    if (!key) return
    // key 形如 `<segId>:<page>:<idx>`：只用到段内页序来定位，页号在第 2 段
    const seg = draft.segs.find((s) => key.startsWith(`${s.id}:`))
    if (!seg) return
    const pageNo = Number(key.split(':')[1])
    const firstPage = seg.refs[0]?.p ?? 1
    const ref = seg.refs[pageNo - firstPage]
    if (!ref) return
    const el = document.querySelector<HTMLElement>(`[data-mi="${ref.mi}"][data-p="${ref.p}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [draft.segs])

  return (
    <>
      {/* 取字 / 选页 顶部提示横条（原型 .pickhint：琥珀底 + Esc）。退出按钮与 Esc 同口径
          （use-reader-keys）：取字态清掉待确认 OCR 与取字目标；选页态清选区并退出模式 */}
      {(pickInfo >= 0 || selMode) && (
        <HintBar mode={pickInfo >= 0 ? 'pick' : 'sel'} field={pickField} onExit={onExitHint} />
      )}

      {/* 三栏主体 */}
      <div className="relative flex min-h-0 flex-1 bg-[#f1f1f3]">
        {narrow && (railOpen || metaOpen) && (
          // 窄屏遮罩：仅 pointer 点按关闭，键盘用户走面板内显式关闭（aria-hidden 不入 tab 序）。
          // absolute 相对三栏主体行（relative）：阅读器右缘已为并排助手收进来，
          // fixed 会把遮罩铺满整个视口、连助手底下的区域也压暗
          <div aria-hidden className="absolute inset-0 z-30 bg-black/20" onClick={onCollapsePanels} />
        )}

        {/* 左栏常驻：「源文件 → 段」的目录是这页的使用习惯，单源单段也不收
            （曾按"内容页流首屏可见"收起过，用户反馈不符合习惯，改回） */}
        <div className={railWrapCls}>
          <Rail
            draft={draft}
            onFocusSeg={onFocusSeg}
            onRenameMat={onRenameMat}
            onRenameSeg={flowOps.renameSeg}
            onSetSegType={flowOps.setSegType}
            onMergeSeg={flowOps.mergeSeg}
            onMergeSegs={flowOps.mergeSegs}
            onMoveSeg={flowOps.moveSeg}
          />
        </div>

        {/* 中栏 = 页面流，**必须自己滚动**。
            外层 FixedReader 是 fixed 全屏 + flex column，中栏 flex-1 撑满剩余高度；
            不给 overflow，内容就会溢出到视口外且没有滚动条 ——
            用户能滚 window（scrollY 会变），但元素位置不动，看起来「卡在第一页」。
            同时把 ref 挂上：useWheelZoom 靠这个元素的 scrollTop/scrollHeight 算缩放锚点。 */}
        <div ref={flowWrapRef} className="relative min-w-0 flex-1 overflow-y-auto overflow-x-hidden">
          <Flow
            draft={draft}
            messageId={messageId}
            pickInfo={pickInfo}
            focusedSeg={focusedSeg}
            zoom={zoom}
            cols={effCols}
            selMode={selMode}
            selPages={selPages}
            ocrPending={ocrPending}
            focusedBlockKey={focusedBlockKey}
            onActivateHit={onActivateHit}
            onOp={flowOps}
            onToggleSel={onToggleSel}
            onOcrBox={onOcrBox}
            onRequestDelete={onRequestDelete}
          />
        </div>

        <div className={metaWrapCls}>
          <MetaPanel
            draft={draft}
            pickInfo={pickInfo}
            onSetPickInfo={onSetPickInfo}
            ops={metaOps}
            focusedSeg={focusedSeg}
            mdOpen={mdOpen}
            onToggleMdOpen={() => setMdOpen((v) => !v)}
            focusedBlockKey={focusedBlockKey}
            onLocateBlock={onLocateBlock}
            editRequestKey={editRequestKey}
            onEditRequestHandled={() => setEditRequestKey(null)}
            narrow={narrow}
          />
        </div>
      </div>

      {/* 选页汇总条 */}
      {selPages.length > 0 && (
        <SelectionBar count={selCount} cross={selCross} onClear={onClearSel} onApply={onApplySel} />
      )}
    </>
  )
}
