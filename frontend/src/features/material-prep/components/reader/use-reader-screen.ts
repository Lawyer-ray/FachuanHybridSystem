import { useMemo } from 'react'
import { useNavigate } from 'react-router'
import { useElementWidth } from '@/hooks/use-element-width'
import { setEngineChecked } from '../../draft'
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
import { useInflightAutoSplit } from './use-auto-split-task'
import { useRedetectParties } from './use-redetect-parties'
import { useReviewBackfill } from './use-review-backfill'
import { useReaderKeys } from './use-reader-keys'
import { useWheelZoom } from './use-wheel-zoom'

/**
 * Reader 的全部接线：store 字段、子 hook、派生量与 props 装配都收在这里，
 * Reader 只负责早返回与布局骨架。
 *
 * 抽出来的原因：Reader 里 20 多个 hook 调用 + 30 行 `bodyProps` 装配占满了
 * 视线，真正决定"这页长什么样"的 JSX 反而被挤到文件末尾。**Hooks 全部在
 * 这个 hook 内部按固定顺序调用**，早返回只发生在 Reader（hooks 之后），
 * 因此 Rules of Hooks 仍然成立。
 *
 * ⚠️ draft 未就绪（未打开 / loading / 打开失败）时**本 hook 内部的字段推导
 * 仍然会执行**——不能假设「Reader 会早返回所以这里安全」。实测踩过：
 * 打开一个刚上传、草稿还没建出来的材料包时，`selDetailOf(readyDraft, …)`
 * 直接读 `d.segs` 抛 `Cannot read properties of null`，整个页面被 ErrorBoundary
 * 接住显示「页面出错了」，用户看到的是白屏。
 * 所以这里对可能为空的 draft 一律做守卫，下面的委托函数也统一收 null。
 */
export function useReaderScreen() {
  const st = useReaderStoreFields()
  const { draft, detail, openId, pickInfo, zoom, cols, selMode, selPages, ocrPending, inconsistencies } = st
  // 不用 `as DraftState` 强行断言：断言会把「可能是 null」这件事从类型里抹掉，
  // 而下面的 selDetailOf / buildFlowOps 都真的会读 draft.segs。保留 null 更诚实。
  const readyDraft = draft ?? null

  // 窄屏形态按**阅读器自身净宽**判定（≤1100 抽屉化）：并排 AI 助手会让位掉
  // 数百像素，视口断点量不到它，宽屏标识配窄屏实际宽度会三栏挤成缝。
  // 首帧宽度未测得（0）先按宽屏渲染，测得后一个断点内翻转一次。
  const [setReaderRef, readerW] = useElementWidth<HTMLDivElement>()
  const narrow = readerW > 0 && readerW <= 1100
  // 中栏滚动容器：宽度测量与滚轮缩放锚点都要它。
  // ⚠️ 这个 ref 必须真的挂到 DOM 上（此前创建了却没挂，见 ReaderBody 的说明）。
  const [setFlowWrap, flowWrapW, flowWrapEl] = useElementWidth<HTMLDivElement>()
  const ocr = useReaderOcr()
  const autoSplit = useAutoSplit()
  // 右栏「重新识别当事人」：自动识别只在分段那一刻跑一次，错了得能重来
  const redetect = useRedetectParties()
  // 打开阅读器就查一次「有没有这个材料包发起、还在跑的识别任务」，命中则接管轮询并
  // 在底部进度面板上显示。以前任务只活在本页面内存里：刷新/换设备后界面一片空白，
  // 而云端那份 164 页卷宗还在烧钱（「幽灵任务」）。
  // 只在草稿就绪时查：mats 来自草稿，没草稿时页数也是猜的。
  // 包号由 useInflightAutoSplit 自己从 store 读（会话态与探测都按包收敛）。
  const inflight = useInflightAutoSplit(readyDraft?.mats ?? [], readyDraft != null)
  // 老草稿缺「复核原因」（source_method）：打开时按 splitRef.jobId 从后端补一次，
  // 否则右栏提示条只能写「置信度 62%」，说不出为什么（见 review-backfill.ts）
  useReviewBackfill(readyDraft, st.update)
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
  // 勾选引擎分歧的「已核对」：走 st.update，与其它草稿编辑同一条持久化路径。
  // 依赖整个 st 而不只是 st.update：eslint 的 exhaustive-deps 不认 `st.update` 这种
  // 属性级依赖（它会要求把 st 整个列进去），而 st 每次渲染都是新对象 -- 所以用 useMemo。
  const toggleEngineChecked = useMemo(
    () => (key: string, checked: boolean) => st.update((d) => setEngineChecked(d, key, checked)),
    [st],
  )
  const metaOps = useMemo(() => buildMetaOps(st.update, st.removeInfo), [st.update, st.removeInfo])

  const launch = useAssignLaunch({
    draft: readyDraft,
    // 归案要拿原始附件，必须有消息 id
    messageId: openId ?? 0,
    // 材料归属里的案件/合同 id 才是项目的锚点；没归到项目就在预处页停下来
    projectId: detail?.draft_state?.assign?.caseId,
    navigate,
    setAssignOpen: st.setAssignOpen,
    setAssign: st.setAssign,
    close: st.close,
    setLaunchFile: view.setLaunchFile,
  })

  const toolbarProps = useReaderToolbarProps({
    // 这里不需要断言：hook 参数本身允许 DraftState | null，内部已做守卫。
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
    focusedSeg: actions.focusedSeg,
    autoSplit,
  })

  const selDetail = readyDraft ? selDetailOf(readyDraft, selPages) : { count: 0, cross: false }
  // 取字目标字段：HintBar 提示与 OCR 确认面板共用同一表达式，只算一遍
  const pickField = readyDraft && pickInfo >= 0 && readyDraft.infos[pickInfo] ? readyDraft.infos[pickInfo].k : ''

  // 三栏主体的 props 一次拼好再展开（ReaderBody 参数多，逐个平铺会让
  // 「谁提供数据」和「怎么排版」混在一起）。
  //
  // 草稿未就绪时整份 props 为 null（Reader 先显示加载骸架）。这样收窄而不用
  // `as DraftState`：断言只在类型层生效，运行期 null 照样会传给下游读 `segs`，
  // 而这正是文件头警告过的那种白屏。
  const bodyProps = !readyDraft
    ? null
    : {
      draft: readyDraft,
      // 页级质量统计与跨页不一致都是「机器读到什么」，旧任务里直接是空 / 缺省
      pageQualityByMi: readyDraft.pageQualityByMi ?? null,
      inconsistencies,
      // 0 = 还没打开任何材料包（与 useAssignLaunch 的 `messageId: openId ?? 0`
      // 同一口径）。不要写成 `openId as number`：断言不会把 null 变成 0，
      // 只会把「可能没打开包」这个真实状态从类型里抹掉。
      messageId: openId ?? 0,
      narrow,
      railOpen: view.railOpen,
      metaOpen: view.metaOpen,
      onOpenMeta: view.openMeta,
      onCollapsePanels: view.collapsePanels,
      railWrapCls: widths.railWrapCls,
      metaWrapCls: widths.metaWrapCls,
      railWrapStyle: widths.railWrapStyle,
      metaWrapStyle: widths.metaWrapStyle,
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
      flowWrapRef: setFlowWrap,
      // 「已核对」是律师的判断，落在草稿上随防抖保存落盘，所以走 st.update 而不是组件 state
      onToggleEngineChecked: toggleEngineChecked,
      // 自动分段进度面板：隐藏时为空（面板自己不渲染），隐藏后任务仍在后台跑
      autoSplitTask: inflight.task.hidden ? null : inflight.task,
      onHideAutoSplit: inflight.hide,
      // 重跑当事人识别（只覆盖机填值，见 use-redetect-parties）
      onRedetectParties: redetect.redetect,
      redetectBusy: redetect.busy,
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
    /** 重跑自动识别前的冲突询问：run() 里挂起，弹窗选完才继续 */
    autoSplit,
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
