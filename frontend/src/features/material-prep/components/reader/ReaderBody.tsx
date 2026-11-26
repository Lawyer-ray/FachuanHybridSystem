import { useCallback, useMemo, useState } from 'react'

import type { DraftState, Inconsistency, OcrPending, PageKey, PageQuality } from '../../types'
import { groupBySeverity, judgeGateNotice, uniqueDisagreementKeys } from '../../draft'
import { useEngineAdopt } from './use-engine-adopt'
import type { useReaderOcr } from './use-ocr'
import { HintBar } from './HintBar'
import { JudgeGateHint } from './JudgeGateHint'
import { ReaderColumns } from './ReaderColumns'
import { ReaderOverlays, type AutoSplitTaskView } from './ReaderOverlays'
import type { buildFlowOps, buildMetaOps } from './reader-ops'
import { useGotoPage } from './use-goto-page'

/**
 * 阅读器三栏主体 + 取字/选页提示条 + 抽屉/浮条。
 *
 * 本文件只做「阅读态与编排」：谁持有哪份 UI 状态、四套跳转怎么接、右栏编辑请求
 * 从哪来。排版下沉到 `ReaderColumns`，浮层下沉到 `ReaderOverlays`，跳转下沉到
 * `use-goto-page`。
 *
 * props 仍然一次收齐（谁提供数据由 Reader 决定）：这里不做数据推导，只把
 * `draft` 派生的少量视图量（分歧唯一键、未核对条数、高亮项）算出来。
 */
export function ReaderBody({
  draft,
  pageQuality = null,
  inconsistencies = [],
  messageId,
  narrow,
  railOpen,
  metaOpen,
  onOpenMeta,
  onCollapsePanels,
  railWrapCls,
  metaWrapCls,
  railWrapStyle,
  metaWrapStyle,
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
  onToggleEngineChecked,
  autoSplitTask = null,
  onHideAutoSplit,
  onRedetectParties,
  redetectBusy = false,
}: {
  draft: DraftState
  /** 页级质量统计（`summary.page_quality`，旧任务为 null） */
  pageQuality?: PageQuality | null
  /** 跨页不一致清单（`summary.inconsistencies`，旧任务为空） */
  inconsistencies?: Inconsistency[]
  messageId: number
  narrow: boolean
  railOpen: boolean
  metaOpen: boolean
  /** 强制展开右栏（窄屏浮层时用；宽屏常驻，幂等） */
  onOpenMeta: () => void
  onCollapsePanels: () => void
  railWrapCls: string
  metaWrapCls: string
  /** 窄屏抽屉宽度（宽屏为 undefined，宽度由拖拽手柄控制） */
  railWrapStyle?: React.CSSProperties
  metaWrapStyle?: React.CSSProperties
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
  /** 勾/取消一条引擎分歧的「已核对」（落在 draft.engineChecked 上，随草稿保存） */
  onToggleEngineChecked: (key: string, checked: boolean) => void
  /** 自动分段任务会话态；null = 没有在跑的任务（或用户点了「不再显示」） */
  autoSplitTask?: AutoSplitTaskView | null
  onHideAutoSplit?: () => void
  /** 重跑当事人识别（只覆盖机填值；无此回调时右栏不显示入口） */
  onRedetectParties?: () => void
  redetectBusy?: boolean
}) {
  // Markdown 面板展开态：右栏自己记，不落草稿（纯阅读偏好）
  const [mdOpen, setMdOpen] = useState(true)
  // 当前高亮的定位块；null = 不预先高亮任何框（一进阅读器满屏重点反而看不出对应关系）
  const [focusedBlockKey, setFocusedBlockKey] = useState<string | null>(null)
  // 全本不一致清单抽屉（入口在左栏顶部）；属于纯阅读态，不落草稿
  const [inconsistencyOpen, setInconsistencyOpen] = useState(false)
  // 全卷「证件页待补录」抽屉（入口同样在左栏顶部，与不一致入口并列）
  const [docTodoOpen, setDocTodoOpen] = useState(false)
  // 双引擎分歧：页面上高亮的那一条
  //
  // 高亮态用**分歧键**而不是下标：重新识别后数组会换一批内容，下标会把高亮挂到
  // 一条不相关的分歧上（乃至越界）。用内容做键，不匹配就自然不高亮。
  const [engineActiveKey, setEngineActiveKey] = useState<string | null>(null)
  // 引用稳定：跳转回调依赖它，每次渲染新建空数组会让回调恒变
  const engineDisagreements = useMemo(() => draft.engineDisagreements ?? [], [draft.engineDisagreements])
  // 「一条一份」的唯一键。不能用裸 `disagreementKey`：同一页内容相近的几条
  // 会算出同一个键（实测 332 条里有 9 组共 27 条撞车），勾选与高亮都会串。
  const engineKeys = useMemo(() => uniqueDisagreementKeys(engineDisagreements), [engineDisagreements])
  const engineKeyToIndex = useMemo(() => {
    const m = new Map<string, number>()
    engineKeys.forEach((k, i) => m.set(k, i))
    return m
  }, [engineKeys])
  const engineFocus = engineActiveKey
    ? (engineDisagreements[engineKeyToIndex.get(engineActiveKey) ?? -1] ?? null)
    : null
  // 左栏徽标只数未核对的：核完的条目仍然留在清单里置灰可查，但不该再催律师
  const engineUnchecked = groupBySeverity(engineDisagreements, new Set(draft.engineChecked ?? [])).unchecked

  // 四套「按页号找段再滚动」的跳转（Markdown / 分歧清单 / 质量提示 / 抽屉共用一份实现）
  const { onGotoSegmentPage, onGotoAnyPage, onLocateBlock, onJumpEngineDisagreement } = useGotoPage({
    segs: draft.segs,
    onFocusSeg,
    onHighlightBlock: setFocusedBlockKey,
    onHighlightEngine: setEngineActiveKey,
    engineKeys,
    engineDisagreements,
  })

  /**
   * 采用某一侧引擎文本 → 直接写入正文 → 保存后自动勾选已核对。
   * 编排逻辑见 `use-engine-adopt.ts`（含「为什么是直接写入」的设计理由）。
   */
  const {
    editRequest,
    adopt: onAdoptEngineText,
    edit: onEditEngineText,
    commit: onEditBlockApplied,
    clearRequest,
    requestEdit,
  } = useEngineAdopt({
    draft,
    focusedSeg,
    editBlock: metaOps.editBlock,
    onToggleChecked: onToggleEngineChecked,
    onGotoPage: onGotoSegmentPage,
    onOpenMd: () => setMdOpen(true),
  })

  /**
   * 双击页面上的定位框 → 高亮 Markdown 对应那条并进入修改态。
   *
   * 与 `onLocateBlock` 是**反向**的两条路：
   *   · onLocateBlock：Markdown → 页面（滚到原页 + 框加亮）
   *   · onActivateHit ：页面 → Markdown（高亮那条 + 直接可改）
   * 律师的直觉是「我在原件上看到这行不对，点它就该能就地改」，
   * 所以这条要走编辑态，而不是只加个高亮。
   */
  const onActivateHit = useCallback(
    (key: string) => {
      setFocusedBlockKey(key)
      requestEdit({ key })
      // 右栏若被折叠，展开它——否则「高亮了但看不见」
      setMdOpen(true)
    },
    [requestEdit],
  )

  /** 左栏「引擎分歧」徽标：展开右栏 + 跳到第一条未核对的分歧 */
  const onOpenEngineDisagreements = () => {
    // 不再有独立页签：分歧已内联在右栏正文之上。这里做两件有实际价值的事——
    // ① 窄屏下把右栏浮层展开（否则点完看不到任何变化）；
    // ② 跳到第一条**未核对**的分歧，律师点徽标的意图就是「带我去看」，
    //    而不是「打开一个空面板」。
    onOpenMeta()
    const checkedSet = new Set(draft.engineChecked ?? [])
    const idx = engineKeys.findIndex((k) => !checkedSet.has(k))
    const first = engineDisagreements[idx === -1 ? 0 : idx]
    if (first) onJumpEngineDisagreement(first.page_no, engineKeys[idx === -1 ? 0 : idx]!)
  }

  return (
    <>
      {/* 取字 / 选页 顶部提示横条（原型 .pickhint：琥珀底 + Esc）。退出按钮与 Esc 同口径
          （use-reader-keys）：取字态清掉待确认 OCR 与取字目标；选页态清选区并退出模式 */}
      {(pickInfo >= 0 || selMode) && (
        <HintBar mode={pickInfo >= 0 ? 'pick' : 'sel'} field={pickField} onExit={onExitHint} />
      )}

      {/* 分歧自动裁定未生效（缺 Key / 总闸没开）：卷级事实，必须跨段常驻。
          没有这一条时，律师只会看到「开关勾着、分歧全进人工」，而界面不解释原因。
          出不出文案全在 `judgeGateNotice` 里：只有「用户要求了但没生效」才出。 */}
      <JudgeGateHint notice={judgeGateNotice(draft.judgeState)} />

      <ReaderColumns
        narrow={narrow}
        railOpen={railOpen}
        metaOpen={metaOpen}
        railWrapCls={railWrapCls}
        metaWrapCls={metaWrapCls}
        railWrapStyle={railWrapStyle}
        metaWrapStyle={metaWrapStyle}
        onCollapsePanels={onCollapsePanels}
        draft={draft}
        pageQuality={pageQuality}
        inconsistencies={inconsistencies}
        engineUnchecked={engineUnchecked}
        onOpenInconsistencies={() => setInconsistencyOpen(true)}
        onOpenDocTodos={() => setDocTodoOpen(true)}
        onOpenEngineDisagreements={onOpenEngineDisagreements}
        onFocusSeg={onFocusSeg}
        onRenameMat={onRenameMat}
        flowOps={flowOps}
        messageId={messageId}
        pickInfo={pickInfo}
        focusedSeg={focusedSeg}
        zoom={zoom}
        effCols={effCols}
        selMode={selMode}
        selPages={selPages}
        ocrPending={ocrPending}
        focusedBlockKey={focusedBlockKey}
        engineFocus={engineFocus}
        onActivateHit={onActivateHit}
        onToggleSel={onToggleSel}
        onOcrBox={onOcrBox}
        onRequestDelete={onRequestDelete}
        flowWrapRef={flowWrapRef}
        onSetPickInfo={onSetPickInfo}
        metaOps={metaOps}
        mdOpen={mdOpen}
        onToggleMdOpen={() => setMdOpen((v) => !v)}
        onLocateBlock={onLocateBlock}
        editRequestKey={editRequest?.key ?? null}
        editRequestSeed={editRequest?.seed ?? null}
        onEditRequestHandled={clearRequest}
        onEditBlockApplied={onEditBlockApplied}
        engineDisagreements={engineDisagreements}
        engineKeys={engineKeys}
        engineChecked={draft.engineChecked ?? []}
        onToggleEngineChecked={onToggleEngineChecked}
        onJumpEngineDisagreement={onJumpEngineDisagreement}
        onAdoptEngineText={onAdoptEngineText}
        onEditEngineText={onEditEngineText}
        onGotoSegmentPage={onGotoSegmentPage}
        onRedetectParties={onRedetectParties}
        redetectBusy={redetectBusy}
      />

      <ReaderOverlays
        inconsistencyOpen={inconsistencyOpen}
        onInconsistencyOpenChange={setInconsistencyOpen}
        inconsistencies={inconsistencies}
        docTodoOpen={docTodoOpen}
        onDocTodoOpenChange={setDocTodoOpen}
        pageQuality={pageQuality}
        onGotoAnyPage={onGotoAnyPage}
        autoSplitTask={autoSplitTask}
        onHideAutoSplit={onHideAutoSplit}
        selPages={selPages}
        selCount={selCount}
        selCross={selCross}
        onClearSel={onClearSel}
        onApplySel={onApplySel}
      />
    </>
  )
}
