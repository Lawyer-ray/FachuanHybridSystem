import { useMemo } from 'react'
import { useNavigate } from 'react-router'
import { useElementWidth } from '@/hooks/use-element-width'
import { buildFlowOps, buildMetaOps, selDetailOf } from './reader-ops'
import { useAssignLaunch } from './use-assign-launch'
import { useReaderStoreFields } from './use-reader-store-fields'
import { useReaderHintExit } from './use-reader-hint-exit'
import { useReaderViewState } from './use-reader-view-state'
import { useReaderToolbarProps } from './use-reader-toolbar-props'
import { useReaderActions } from './use-reader-actions'
import { useReaderWidths } from './use-reader-widths'
import { useReaderOcr } from './use-ocr'
import { useAutoSplit } from './use-auto-split'
import { useReaderKeys } from './use-reader-keys'
import { useWheelZoom } from './use-wheel-zoom'
import type { DraftState } from '../../types'

/**
 * Reader 的全部接线：store 字段、子 hook、派生量与 props 装配都收在这里，
 * Reader 只负责早返回与布局骨架。
 *
 * 抽出来的原因：Reader 里 20 多个 hook 调用 + 30 行 `bodyProps` 装配占满了
 * 视线，真正决定"这页长什么样"的 JSX 反而被挤到文件末尾。**Hooks 全部在
 * 这个 hook 内部按固定顺序调用**，早返回只发生在 Reader（hooks 之后），
 * 因此 Rules of Hooks 仍然成立。
 *
 * draft 未就绪（未打开 / loading）时按空值兜底：此时 Reader 早早返回
 * loading / null，这里的产物不会被渲染。
 */
export function useReaderScreen() {
  const st = useReaderStoreFields()
  const { draft, detail, openId, pickInfo, zoom, cols, selMode, selPages, ocrPending } = st
  const readyDraft = draft as DraftState

  // 窄屏形态按**阅读器自身净宽**判定（≤1100 抽屉化）：并排 AI 助手会让位掉
  // 数百像素，视口断点量不到它，宽屏标识配窄屏实际宽度会三栏挤成缝。
  // 首帧宽度未测得（0）先按宽屏渲染，测得后一个断点内翻转一次。
  const [setReaderRef, readerW] = useElementWidth<HTMLDivElement>()
  const narrow = readerW > 0 && readerW <= 1100
  const [, flowWrapW, flowWrapEl] = useElementWidth<HTMLDivElement>()
  const ocr = useReaderOcr()
  const autoSplit = useAutoSplit()
  const actions = useReaderActions(draft)
  const view = useReaderViewState()
  const onExitHint = useReaderHintExit()
  const navigate = useNavigate()

  useReaderKeys()
  // ⌘/Ctrl + 滚轮（含触控板捏合）缩放画布，挂在中栏滚动容器上
  useWheelZoom(flowWrapEl, zoom)

  const widths = useReaderWidths({
    cols,
    flowWrapW,
    narrow,
    railOpen: view.railOpen,
    metaOpen: view.metaOpen,
  })

  // ops 稳定化：让 Flow → PageCell 的 memo 真正命中（st.update / pickPage 都是稳定引用）
  const flowOps = useMemo(() => buildFlowOps(st.update, ocr.pickPage), [st.update, ocr.pickPage])
  const metaOps = useMemo(() => buildMetaOps(st.update, st.removeInfo), [st.update, st.removeInfo])

  const launch = useAssignLaunch({
    draft: readyDraft,
    // 材料归属里的案件/合同 id 才是项目的锚点；没归到项目就在预处页停下来
    projectId: detail?.draft_state?.assign?.caseId,
    navigate,
    setAssignOpen: st.setAssignOpen,
    setAssign: st.setAssign,
    close: st.close,
    setLaunchFile: view.setLaunchFile,
  })

  const toolbarProps = useReaderToolbarProps({
    draft: readyDraft,
    railOpen: view.railOpen,
    metaOpen: view.metaOpen,
    onToggleRail: view.toggleRail,
    onToggleMeta: view.toggleMeta,
    onCollapsePanels: view.collapsePanels,
    maxColsAllowed: widths.maxCols,
    effCols: widths.effCols,
    zoom,
    zoomIn: actions.zoomIn,
    zoomOut: actions.zoomOut,
    onResetSegments: actions.onResetSegments,
    onFocusSeg: actions.focusSeg,
    addInput: view.addInput,
    autoSplit,
  })

  const selDetail = selDetailOf(readyDraft, selPages)
  // 取字目标字段：HintBar 提示与 OCR 确认面板共用同一表达式，只算一遍
  const pickField = pickInfo >= 0 && readyDraft?.infos[pickInfo] ? readyDraft.infos[pickInfo].k : ''

  // 三栏主体的 props 一次拼好再展开（ReaderBody 参数多，逐个平铺会让
  // 「谁提供数据」和「怎么排版」混在一起）
  const bodyProps = {
    draft: readyDraft,
    messageId: openId as number,
    narrow,
    railOpen: view.railOpen,
    metaOpen: view.metaOpen,
    onCollapsePanels: view.collapsePanels,
    railWrapCls: widths.railWrapCls,
    metaWrapCls: widths.metaWrapCls,
    pickInfo,
    pickField,
    selMode,
    selPages,
    // 选页汇总条只数当前选区（跨段时文案不同）
    selCount: selDetail.count,
    selCross: selDetail.cross,
    focusedSeg: actions.focusedSeg,
    zoom,
    effCols: widths.effCols,
    ocrPending,
    flowOps,
    metaOps,
    onToggleSel: st.onToggleSel,
    onOcrBox: ocr.onOcrBox,
    onRequestDelete: actions.setDeleteTarget,
    onFocusSeg: actions.focusSeg,
    onRenameMat: view.startRenameMat,
    onSetPickInfo: st.setPickInfo,
    onClearSel: st.clearSel,
    onApplySel: st.applySel,
    onExitHint,
  }

  return {
    // 逐个解构而不是把 st / ocr / actions / view 整个返回：React Compiler 的 ref 规则
    // 会把「含 useRef 的 hook（含自定义 hook）返回值」当 ref 对象，整个返回后消费端读
    // 任何字段都会被判成 "access ref during render"。分开给值就没有这个歧义。
    data: { draft, detail, openId, ocrPending },
    meta: { status: st.status, error: st.error, closing: st.closing },
    store: {
      close: st.close,
      setAssignOpen: st.setAssignOpen,
      setPickInfo: st.setPickInfo,
      setOcrPending: st.setOcrPending,
      appendFiles: st.appendFiles,
    },
    ocrOk: ocr.ocrOk,
    showAssign: st.assignOpen,
    actions: {
      onReject: actions.onReject,
      confirmDelete: actions.confirmDelete,
      setDeleteTarget: actions.setDeleteTarget,
      deleteTarget: actions.deleteTarget,
    },
    renaming: view.renaming,
    setRenaming: view.setRenaming,
    renameMat: view.renameMat,
    setRenameMat: view.setRenameMat,
    /** 回调 ref：直接给 <input ref={...}> 用，渲染期不碰 .current */
    setAddInputRef: view.setAddInputRef,
    // 回调 ref：消费端直接 rootRef={readerRef}，渲染期不读 .current
    readerRef: setReaderRef,
    launchFile: view.launchFile,
    launch,
    narrow,
    toolbarProps,
    bodyProps,
    pickField,
  }
}
