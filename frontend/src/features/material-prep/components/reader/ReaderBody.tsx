import { useCallback, useMemo, useState } from 'react'

import type { DraftState, Inconsistency, OcrPending, PageKey, PageQuality } from '../../types'
import { groupBySeverity, uniqueDisagreementKeys } from '../../draft'
import { blockKeyOf } from '../../draft/block-keys'
import { scrollToEngineRects } from './scroll-to-rect'
import type { useReaderOcr } from './use-ocr'
import { Flow } from './Flow'
import { DocTodoDrawer } from './DocTodoDrawer'
import { InconsistencyDrawer } from './InconsistencyDrawer'
import { AutoSplitProgress } from './AutoSplitProgress'
import { HintBar } from './HintBar'
import { MetaPanel } from './MetaPanel'
import { Rail } from './Rail'
import { SelectionBar } from './SelectionBar'
import type { buildFlowOps, buildMetaOps } from './reader-ops'
import type { JobProgressSnapshot } from './auto-split-helpers'

/** 自动分段任务会话态（结构由 use-auto-split-task 定义；这里只要面板用得到的那部分） */
type AutoSplitTaskView = {
  jobId: string | null
  snapshot: JobProgressSnapshot | null
  /** 本页面亲自发起的任务（接管来的只展示、不回写草稿） */
  owned: boolean
}

/**
 * 阅读器三栏主体 + 取字/选页提示条 + 选页汇总条。
 *
 * 从 Reader 抽出来的原因很单纯：这一段是"纯 JSX 装配"（没有任何状态与派生），
 * 却是 Reader 里最长的部分，把它留在顶层编排里，topbar / dialogs / 抽屉的
 * 接线就被挤到看不见。这里只收 props，谁提供数据由 Reader 决定。
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
  // 全本不一致清单抽屉（入口在左栏顶部）；属于纯阅读态，不落草稿
  const [inconsistencyOpen, setInconsistencyOpen] = useState(false)
  // 全卷「证件页待补录」抽屉（入口同样在左栏顶部，与不一致入口并列）
  const [docTodoOpen, setDocTodoOpen] = useState(false)
  // 双引擎分歧抽屉 + 当前在页面上高亮的那一条
  //
  // 高亮态用**分歧键**而不是下标：重新识别后数组会换一批内容，下标会把高亮挂到
  // 一条不相关的分歧上（乃至越界）。用内容做键，不匹配就自然不高亮。
  const [engineActiveKey, setEngineActiveKey] = useState<string | null>(null)
  // 引用稳定：下面 onJumpEngineDisagreement 依赖它，每次渲染新建空数组会让回调恒变
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

  /**
   * 质量提示条 → 原页：滚到那一段（段内页卡带有 `data-mi` / `data-p`）。
   * 用段做跳转而不是全局页表：段的页卡与律师看到的那一段正文是同一个东西，
   * 跳过去不会让人「知道在第 147 页，却在长列表里找不到」。
   */
  const onGotoSegmentPage = useCallback(
    (si: number, p: number) => {
      const ref = draft.segs[si]?.refs.find((r) => r.p === p)
      if (!ref) return
      onFocusSeg(si)
      document.querySelector<HTMLElement>(`[data-mi="${ref.mi}"][data-p="${ref.p}"]`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      })
    },
    [draft.segs, onFocusSeg],
  )

  /** 不一致清单是**全本视角**，只给了一个页号；按页号在草稿里找它所在的段再跳 */
  const onGotoAnyPage = useCallback(
    (p: number) => {
      // 多源材料包里同一页码可能出现多次（每份 PDF 都从 1 开始），取第一个能定位到的
      const si = draft.segs.findIndex((s) => s.refs.some((r) => r.p === p))
      if (si < 0) return
      const ref = draft.segs[si]!.refs.find((r) => r.p === p)!
      onFocusSeg(si)
      document.querySelector<HTMLElement>(`[data-mi="${ref.mi}"][data-p="${ref.p}"]`)?.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      })
    },
    [draft.segs, onFocusSeg],
  )

  /**
   * 点一条引擎分歧：滚到那一页 + 记住高亮（Flow 据此在该页画两个引擎的框）。
   *
   * 与 `onGotoAnyPage` 共用「按页号找段」的口径（多源包里同一页码可能出现多次）。
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
      // 也不能用下标：抽屉里的分组会按严重度重排，组内下标与这里的全局下标
      // 不是一回事，拿它索引会高亮到别的条目上。键是内容派生的，不受排序影响。
      setEngineActiveKey(key)
      onGotoAnyPage(pageNo)

      // 再滚到**框的位置**（不只是页顶）：一页上千像素高，只到页顶等于没定位。
      // 没有块坐标时（约 11%）该函数直接返回，保持「只跳页」不伪造精度。
      const item = engineDisagreements.find((d, i) => engineKeys[i] === key)
      const si = draft.segs.findIndex((sg) => sg.refs.some((r) => r.p === pageNo))
      if (si < 0) return
      const ref = draft.segs[si]!.refs.find((r) => r.p === pageNo)
      if (!ref) return
      scrollToEngineRects(ref.mi, ref.p, item?.blocks ?? [])
    },
    [onGotoAnyPage, engineDisagreements, engineKeys, draft.segs],
  )

  const onLocateBlock = useCallback((key: string | null) => {
    setFocusedBlockKey(key)
    if (!key) return
    // key 形如 `<segId>:<page>:<idx>`：只用到段内页序来定位，页号在第 2 段
    const seg = draft.segs.find((s) => key.startsWith(`${s.id}:`))
    if (!seg) return
    const pageNo = Number(key.split(':')[1])
    // 按页号 find，不能用 `page_no - firstPage` 当下标：切出几页 / 删页之后
    // refs 可以是 [1, 3, 7] 这种跳号序列，减法会错位到别的页上。
    const ref = seg.refs.find((r) => r.p === pageNo)
    if (!ref) return
    const el = document.querySelector<HTMLElement>(`[data-mi="${ref.mi}"][data-p="${ref.p}"]`)
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }, [draft.segs])

  /**
   * 采用某一侧引擎的这行文字，写回正文对应块。
   *
   * ## 为什么这是「省打字」而不是「替律师裁决」
   *
   * 旧的组件注释说「刻意不提供采纳某个引擎的按钮：按钮一按下去，错的那份就进了
   * 诉状引用」。那句话在**没法核对**时成立。但现在律师旁边就是原件、有双框标注、
   * 有跳转——他点「采用」之前必须自己看着原件判断。此时按钮的价值是把判定的结果
   * **抄进正文**，免掉手工比对与打字，而不是替他决定。
   *
   * ## 定位口径
   *
   * 用引擎文本去 `seg.blocks` 里找包含它的那一块（与 `locateKeyOf` 同一思路：
   * block 的 page 与分歧页号必须一致）。找不到就什么都不做——宁可不改，
   * 也不要把文字写到错误的块上。
   */
  const onAdoptEngineText = useCallback(
    (pageNo: number, text: string, _engine: string) => {
      const seg = draft.segs[focusedSeg]
      if (!seg?.blocks?.length) return
      const needle = text.trim()
      if (!needle) return
      const idx = seg.blocks.findIndex((b) => b.page === pageNo && (b.text ?? '').includes(needle))
      if (idx < 0) return
      const block = seg.blocks[idx]!
      const key = blockKeyOf(seg, block, idx)
      metaOps.editBlock(focusedSeg, key, needle)
      setFocusedBlockKey(key)
      onGotoSegmentPage(focusedSeg, pageNo)
    },
    [draft.segs, focusedSeg, metaOps, onGotoSegmentPage],
  )

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
            pageQuality={pageQuality}
            inconsistencies={inconsistencies}
            onOpenInconsistencies={() => setInconsistencyOpen(true)}
            onOpenDocTodos={() => setDocTodoOpen(true)}
            engineUnchecked={engineUnchecked}
            onOpenEngineDisagreements={() => {
              // 不再有独立页签：分歧已内联在右栏正文之上。这里做两件有实际价值的事——
              // ① 窄屏下把右栏浮层展开（否则点完看不到任何变化）；
              // ② 跳到第一条**未核对**的分歧，律师点徽标的意图就是「带我去看」，
              //    而不是「打开一个空面板」。
              onOpenMeta()
              const checkedSet = new Set(draft.engineChecked ?? [])
              const idx = engineKeys.findIndex((k) => !checkedSet.has(k))
              const first = engineDisagreements[idx === -1 ? 0 : idx]
              if (first) onJumpEngineDisagreement(first.page_no, engineKeys[idx === -1 ? 0 : idx]!)
            }}
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

        <div className={metaWrapCls}>
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
            onToggleMdOpen={() => setMdOpen((v) => !v)}
            focusedBlockKey={focusedBlockKey}
            onLocateBlock={onLocateBlock}
            editRequestKey={editRequestKey}
            onEditRequestHandled={() => setEditRequestKey(null)}
            narrow={narrow}
            engineItems={engineDisagreements}
            engineKeys={engineKeys}
            engineChecked={draft.engineChecked ?? []}
            onToggleEngineChecked={onToggleEngineChecked}
            onJumpEngine={onJumpEngineDisagreement}
            onAdoptEngine={onAdoptEngineText}
          />
        </div>
      </div>

      {/* 全本跨页不一致清单：从左栏徽标打开，点页号直接跳到那一页 */}
      <InconsistencyDrawer
        open={inconsistencyOpen}
        onOpenChange={setInconsistencyOpen}
        items={inconsistencies}
        onGotoPage={onGotoAnyPage}
      />

      {/* 全卷证件页待补录：从左栏证件徽标打开，「查看原页」跳到那一页 */}
      <DocTodoDrawer
        open={docTodoOpen}
        onOpenChange={setDocTodoOpen}
        pageQuality={pageQuality}
        onGotoPage={onGotoAnyPage}
      />

      {/* 自动分段进度：底部浮条，与选页汇总条同一范式（不参与 flex 高度分配，
          不给中栏的 overflow 加滚动耦合）。没有快照时显示「准备中」——提交 164 页
          本身要几十秒，那段空白期也得有反馈。 */}
      {autoSplitTask &&
        (autoSplitTask.jobId || autoSplitTask.snapshot) && (
          <AutoSplitProgress
            snapshot={autoSplitTask.snapshot ?? pendingSnapshot(autoSplitTask.jobId)}
            onDismiss={onHideAutoSplit ?? (() => {})}
          />
        )}

      {/* 选页汇总条 */}
      {selPages.length > 0 && (
        <SelectionBar count={selCount} cross={selCross} onClear={onClearSel} onApply={onApplySel} />
      )}
    </>
  )
}

/** 刚提交、还没轮询到第一份快照时的占位：进度 0、阶段取字、「正在识别文字」 */
function pendingSnapshot(jobId: string | null): JobProgressSnapshot {
  return {
    jobId: jobId ?? '',
    status: 'pending',
    stage: '',
    progressPct: 0,
    processedPages: 0,
    totalPages: 0,
    elapsedSeconds: null,
    staleSeconds: null,
    errorMessage: '',
    dualEngines: '',
    sourceName: '',
  }
}
