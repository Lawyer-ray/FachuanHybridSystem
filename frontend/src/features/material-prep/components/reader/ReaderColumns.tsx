import type { DraftState, EngineDisagreement, Inconsistency, OcrPending, PageKey, PageQuality } from '../../types'
import type { useReaderOcr } from './use-ocr'
import type { buildFlowOps, buildMetaOps } from './reader-ops'
import { Flow } from './Flow'
import { MetaPanel } from './MetaPanel'
import { Rail } from './Rail'

/**
 * 阅读器三栏（左目录 / 中页面流 / 右正文）+ 窄屏遮罩。
 *
 * 从 ReaderBody 拆出：ReaderBody 只保留阅读态与跳转编排，排版这一层不再和
 * 「谁提供数据」混在一个函数里。三个栏的 props 在这里直接分发给 Rail / Flow /
 * MetaPanel，不给中间层再转一遍手。
 */
export function ReaderColumns({
  // 布局
  narrow,
  railOpen,
  metaOpen,
  railWrapCls,
  metaWrapCls,
  railWrapStyle,
  metaWrapStyle,
  onCollapsePanels,
  // 左栏
  draft,
  pageQuality,
  inconsistencies,
  engineUnchecked,
  onOpenInconsistencies,
  onOpenDocTodos,
  onOpenEngineDisagreements,
  onFocusSeg,
  onRenameMat,
  flowOps,
  // 中栏
  messageId,
  pickInfo,
  focusedSeg,
  zoom,
  effCols,
  selMode,
  selPages,
  ocrPending,
  focusedBlockKey,
  engineFocus,
  onActivateHit,
  onToggleSel,
  onOcrBox,
  onRequestDelete,
  flowWrapRef,
  // 右栏
  onSetPickInfo,
  metaOps,
  mdOpen,
  onToggleMdOpen,
  onLocateBlock,
  editRequestKey,
  editRequestSeed,
  onEditRequestHandled,
  onEditBlockApplied,
  engineDisagreements,
  engineKeys,
  engineChecked,
  onToggleEngineChecked,
  onJumpEngineDisagreement,
  onAdoptEngineText,
  onEditEngineText,
  onGotoSegmentPage,
  onRedetectParties,
  redetectBusy,
}: {
  narrow: boolean
  railOpen: boolean
  metaOpen: boolean
  railWrapCls: string
  metaWrapCls: string
  /** 窄屏抽屉宽度（宽屏为 undefined：宽度由 Rail / MetaPanel 的拖拽手柄控制） */
  railWrapStyle?: React.CSSProperties
  metaWrapStyle?: React.CSSProperties
  onCollapsePanels: () => void
  draft: DraftState
  pageQuality: PageQuality | null
  inconsistencies: Inconsistency[]
  /** 左栏徽标数字：只数未核对的引擎分歧 */
  engineUnchecked: number
  onOpenInconsistencies: () => void
  onOpenDocTodos: () => void
  onOpenEngineDisagreements: () => void
  onFocusSeg: (si: number) => void
  onRenameMat: (mi: number) => void
  flowOps: ReturnType<typeof buildFlowOps>
  messageId: number
  pickInfo: number
  focusedSeg: number
  zoom: number
  effCols: number
  selMode: boolean
  selPages: PageKey[]
  ocrPending: OcrPending | null
  focusedBlockKey: string | null
  engineFocus: EngineDisagreement | null
  onActivateHit: (key: string) => void
  onToggleSel: (mi: number, p: number, shift: boolean) => void
  onOcrBox: ReturnType<typeof useReaderOcr>['onOcrBox']
  onRequestDelete: (picked: PageKey[]) => void
  flowWrapRef: (node: HTMLDivElement | null) => void
  onSetPickInfo: (i: number) => void
  metaOps: ReturnType<typeof buildMetaOps>
  mdOpen: boolean
  onToggleMdOpen: () => void
  onLocateBlock: (key: string | null) => void
  editRequestKey: string | null
  editRequestSeed: string | null | undefined
  onEditRequestHandled: () => void
  onEditBlockApplied: () => void
  engineDisagreements: EngineDisagreement[]
  engineKeys: string[]
  engineChecked: string[]
  onToggleEngineChecked: (key: string, checked: boolean) => void
  onJumpEngineDisagreement: (pageNo: number, key: string) => void
  onAdoptEngineText: (pageNo: number, text: string, disagreeKey?: string) => void
  onEditEngineText: (pageNo: number, text: string, disagreeKey?: string) => void
  onGotoSegmentPage: (si: number, p: number) => void
  onRedetectParties?: () => void
  redetectBusy?: boolean
}) {
  return (
    <div className="relative flex min-h-0 flex-1 bg-[#f1f1f3]">
      {narrow && (railOpen || metaOpen) && (
        // 窄屏遮罩：仅 pointer 点按关闭，键盘用户走面板内显式关闭（aria-hidden 不入 tab 序）。
        // absolute 相对三栏主体行（relative）：阅读器右缘已为并排助手收进来，
        // fixed 会把遮罩铺满整个视口、连助手底下的区域也压暗
        <div aria-hidden className="absolute inset-0 z-30 bg-black/20" onClick={onCollapsePanels} />
      )}

      {/* 左栏常驻：「源文件 → 段」的目录是这页的使用习惯，单源单段也不收
          （曾按"内容页流首屏可见"收起过，用户反馈不符合习惯，改回） */}
      <div className={railWrapCls} style={railWrapStyle}>
        <Rail
          draft={draft}
          pageQuality={pageQuality}
          inconsistencies={inconsistencies}
          onOpenInconsistencies={onOpenInconsistencies}
          onOpenDocTodos={onOpenDocTodos}
          engineUnchecked={engineUnchecked}
          onOpenEngineDisagreements={onOpenEngineDisagreements}
          onFocusSeg={onFocusSeg}
          onRenameMat={onRenameMat}
          onRenameSeg={flowOps.renameSeg}
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
          engineFocus={engineFocus}
          onActivateHit={onActivateHit}
          onOp={flowOps}
          onToggleSel={onToggleSel}
          onOcrBox={onOcrBox}
          onRequestDelete={onRequestDelete}
        />
      </div>

      <div className={metaWrapCls} style={metaWrapStyle}>
        {/* 右栏单一栏，不再分页签：正文 / 本段分歧 / 字段便签三者的作用域
            都是「当前这一段」，分页签会把「发现问题」与「修复问题」拆到两个屏上。
            分歧内联在正文之上（见 EngineDisagreementsInline 的注释）。
            ⚠ 也不再用模态 Sheet：遮罩会把整页压灰并拦截点击，而核对分歧必须
            在原件上边看边改——设计意图（「抽屉不关」）与模态实现本来就矛盾。 */}
        <MetaPanel
          draft={draft}
          pageQuality={pageQuality}
          onGotoPage={onGotoSegmentPage}
          pickInfo={pickInfo}
          onSetPickInfo={onSetPickInfo}
          ops={metaOps}
          focusedSeg={focusedSeg}
          mdOpen={mdOpen}
          onToggleMdOpen={onToggleMdOpen}
          focusedBlockKey={focusedBlockKey}
          onLocateBlock={onLocateBlock}
          editRequestKey={editRequestKey}
          editRequestSeed={editRequestSeed}
          onEditRequestHandled={onEditRequestHandled}
          onEditBlockApplied={onEditBlockApplied}
          narrow={narrow}
          engineItems={engineDisagreements}
          engineKeys={engineKeys}
          engineChecked={engineChecked}
          onToggleEngineChecked={onToggleEngineChecked}
          onJumpEngine={onJumpEngineDisagreement}
          onAdoptEngine={onAdoptEngineText}
          onEditEngine={onEditEngineText}
          inconsistencies={inconsistencies}
          onRedetectParties={onRedetectParties}
          redetectBusy={redetectBusy}
        />
      </div>
    </div>
  )
}
