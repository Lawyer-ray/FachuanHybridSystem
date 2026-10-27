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
}) {
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

        <div className="relative min-w-0 flex-1">
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
            onOp={flowOps}
            onToggleSel={onToggleSel}
            onOcrBox={onOcrBox}
            onRequestDelete={onRequestDelete}
          />
        </div>

        <div className={metaWrapCls}>
          <MetaPanel draft={draft} pickInfo={pickInfo} onSetPickInfo={onSetPickInfo} ops={metaOps} />
        </div>
      </div>

      {/* 选页汇总条 */}
      {selPages.length > 0 && (
        <SelectionBar count={selCount} cross={selCross} onClear={onClearSel} onApply={onApplySel} />
      )}
    </>
  )
}
