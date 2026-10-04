import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useReader } from '../../store'
import { countUnclassified, matLabel } from '../../draft'
import { useMediaQuery } from '@/hooks/use-media'
import { ReaderTopBar } from './ReaderTopBar'
import { ReaderToolbar } from './ReaderToolbar'
import { HintBar } from './HintBar'
import { SelectionBar } from './SelectionBar'
import { KeyHintsBar } from './KeyHintsBar'
import { Rail } from './Rail'
import { Flow } from './Flow'
import { MetaPanel } from './MetaPanel'
import { useReaderOcr } from './use-ocr'
import { useAutoSplit } from './use-auto-split'
import { useElementWidth } from '../../hooks/use-element-width'
import { useReaderKeys } from './use-reader-keys'
import { useReaderWidths } from './use-reader-widths'
import { buildFlowOps, buildMetaOps, selDetailOf } from './reader-ops'
import { ReaderDialogs } from './ReaderDialogs'
import { useReaderActions } from './use-reader-actions'
import { cn } from '@/lib/utils'

/** 阅读器：阅读器顶层编排。状态、loading/error 分支、三栏布局组合，
 *  具体的 ops / 键位 / 列宽 / 弹窗各自下沉到子模块。 */
export function Reader() {
  // 按字段 selector 订阅，避免 store 任一字段变化触发 Reader 整树重渲染
  const openId = useReader((s) => s.openId)
  const detail = useReader((s) => s.detail)
  const draft = useReader((s) => s.draft)
  const status = useReader((s) => s.status)
  const closing = useReader((s) => s.closing)
  const pickInfo = useReader((s) => s.pickInfo)
  const zoom = useReader((s) => s.zoom)
  const cols = useReader((s) => s.cols)
  const selMode = useReader((s) => s.selMode)
  const selPages = useReader((s) => s.selPages)
  const ocrPending = useReader((s) => s.ocrPending)
  const assignOpen = useReader((s) => s.assignOpen)
  const setAssignOpen = useReader((s) => s.setAssignOpen)
  const error = useReader((s) => s.error)
  // 待重命名的源文件（左栏重命名入口打开），null = 关闭
  const [renameMat, setRenameMat] = useState<{ mi: number; initial: string } | null>(null)
  const [renaming, setRenaming] = useState(false)
  const [railOpen, setRailOpen] = useState(false)
  const [metaOpen, setMetaOpen] = useState(false)
  const addInputRef = useRef<HTMLInputElement>(null)
  const narrow = useMediaQuery('(max-width:1100px)')
  const [flowWrapRef, flowWrapW] = useElementWidth<HTMLDivElement>()
  const { pickPage, onOcrBox, ocrOk } = useReaderOcr()
  const autoSplit = useAutoSplit()
  const {
    focusedSeg,
    focusSeg,
    deleteTarget,
    setDeleteTarget,
    zoomIn,
    zoomOut,
    onComplete,
    onResetSegments,
    onReject,
    confirmDelete,
  } = useReaderActions(draft)

  const st = useReader.getState()

  useReaderKeys()

  const { maxCols: maxColsAllowed, effCols, railWrapCls, metaWrapCls } = useReaderWidths({
    cols,
    flowWrapW,
    narrow,
    railOpen,
    metaOpen,
  })

  useEffect(() => {
    setRailOpen(false)
    setMetaOpen(false)
    setRenameMat(null)
    setAssignOpen(false)
  }, [openId, setAssignOpen])

  // 框选取字必须看得见页面 —— 抽屉让开
  useEffect(() => {
    if (pickInfo >= 0) {
      setRailOpen(false)
      setMetaOpen(false)
    }
  }, [pickInfo])

  // ops 稳定化：让 Flow → PageCell 的 memo 真正命中（st.update / pickPage 都是稳定引用）。
  // 放 early return 之前（不依赖 draft），符合 Rules of Hooks
  const flowOps = useMemo(() => buildFlowOps(st.update, pickPage), [st.update, pickPage])
  const metaOps = useMemo(() => buildMetaOps(st.update, st.removeInfo), [st.update, st.removeInfo])
  // 同理：内联箭头会让 Flow 的 cellPropsOf 依赖每次 render 变化，PageCell memo 全失效
  // ——直接 selector 取 store 里的稳定函数引用（zustand action 引用恒不变）
  const onToggleSel = useReader((s) => s.toggleSel)

  if (!openId || !detail) return null

  const close = () => st.close()

  if (status === 'loading' || !draft) {
    return (
      <FixedReader>
        <div className="flex flex-1 items-center justify-center gap-2 text-sm text-secondary-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> 正在打开材料包，解析页数…
        </div>
      </FixedReader>
    )
  }

  if (status === 'error') {
    return (
      <FixedReader>
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-sm">
          <p className="text-destructive">{error}</p>
          <Button onClick={close}>返回</Button>
        </div>
      </FixedReader>
    )
  }

  const unclassified = countUnclassified(draft)
  const allClassified = draft.segs.length > 0 && unclassified === 0
  const pages = draft.mats.reduce((s, m) => s + m.pages, 0)
  const selDetail = selDetailOf(draft, selPages)

  const changeCols = () => {
    // 窗口不够宽就点不动（列数按钮已禁用）
    if (maxColsAllowed <= 1) return
    // 原型行为：在「1 列」和「当前窗口上限」之间循环，而不是写死上到 3
    const next = effCols >= maxColsAllowed ? 1 : effCols + 1
    st.setCols(next)
    // 多列时收起侧栏，让页面更宽敞
    if (next > 1) {
      setRailOpen(false)
      setMetaOpen(false)
    }
  }

  const zoomVal = Math.round(zoom * 100)

  const ocrFrom = ocrPending ? `${matLabel(draft.mats, ocrPending.mi)} P${ocrPending.p}` : ''
  // 取字目标字段：HintBar 提示与 OCR 确认面板共用同一表达式，只算一遍
  const pickField = pickInfo >= 0 && draft.infos[pickInfo] ? draft.infos[pickInfo].k : ''

  return (
    <FixedReader closing={closing}>
      <ReaderTopBar
        title={detail.subject || '材料包'}
        subtitle={`${draft.mats.length} 个源文件 · ${pages} 页 · ${draft.segs.length} 份材料 · ${unclassified} 段未归类`}
        allClassified={allClassified}
        onBack={close}
        onReject={onReject}
        onAssign={() => setAssignOpen(true)}
        onClose={close}
        onRename={() => setRenaming(true)}
      />

      <ReaderToolbar
        narrow={narrow}
        railOpen={railOpen}
        metaOpen={metaOpen}
        onToggleRail={() => {
          setRailOpen((v) => !v)
          setMetaOpen(false)
        }}
        onToggleMeta={() => {
          setMetaOpen((v) => !v)
          setRailOpen(false)
        }}
        progressText={`${draft.mats.length} 个源文件 · ${pages} 页`}
        selMode={selMode}
        onToggleSelMode={() => st.toggleSelMode()}
        onAddFiles={() => addInputRef.current?.click()}
        zoomVal={zoomVal}
        onZoomIn={zoomIn}
        onZoomOut={zoomOut}
        onZoomReset={() => st.setZoom(1)}
        cols={effCols}
        colsDisabled={maxColsAllowed <= 1}
        onChangeCols={changeCols}
        onResetSegments={onResetSegments}
        onAutoSplit={() => void autoSplit.run()}
        autoSplitRunning={autoSplit.running}
        autoSplitProgress={autoSplit.progress}
        onComplete={onComplete}
      />

      {/* 取字 / 选页 顶部提示横条（原型 .pickhint：琥珀底 + Esc） */}
      {(pickInfo >= 0 || selMode) && <HintBar mode={pickInfo >= 0 ? 'pick' : 'sel'} field={pickField} />}

      {/* 三栏主体 */}
      <div className="relative flex min-h-0 flex-1 bg-[#f1f1f3]">
        {narrow && (railOpen || metaOpen) && (
          // 窄屏遮罩：仅 pointer 点按关闭，键盘用户走面板内显式关闭（aria-hidden 不入 tab 序）
          <div
            aria-hidden
            className="fixed inset-0 z-30 bg-black/20"
            onClick={() => {
              setRailOpen(false)
              setMetaOpen(false)
            }}
          />
        )}

        <div className={railWrapCls}>
          <Rail
            draft={draft}
            onFocusSeg={focusSeg}
            onRenameMat={(mi) => {
              const m = draft.mats[mi]!
              setRenameMat({ mi, initial: m.customName || m.n })
            }}
          />
        </div>

        <div ref={flowWrapRef} className="relative min-w-0 flex-1 overflow-auto">
          <Flow
            draft={draft}
            messageId={openId}
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
            onRequestDelete={(picked) => setDeleteTarget(picked)}
          />
        </div>

        <div className={metaWrapCls}>
          <MetaPanel
            draft={draft}
            pickInfo={pickInfo}
            onSetPickInfo={(i) => st.setPickInfo(i)}
            ops={metaOps}
          />
        </div>
      </div>

      {/* 选页汇总条 */}
      {selPages.length > 0 && (
        <SelectionBar
          count={selDetail.count}
          cross={selDetail.cross}
          onClear={() => st.clearSel()}
          onApply={() => st.applySel()}
        />
      )}

      {/* 底栏：键位提示 + 进度 */}
      <KeyHintsBar allClassified={allClassified} unclassified={unclassified} />

      {/* 追加材料文件选择 */}
      <input
        ref={addInputRef}
        type="file"
        multiple
        accept=".pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.jpg,.jpeg,.png,.webp,.heic,.mp4,.mov"
        className="hidden"
        onChange={(e) => {
          if (e.target.files && e.target.files.length) void st.appendFiles(Array.from(e.target.files))
          e.target.value = ''
        }}
      />

      <ReaderDialogs
        draft={draft}
        detail={detail}
        ocrPending={ocrPending}
        ocrFrom={ocrFrom}
        ocrTo={pickField}
        onOcrText={(v) => {
          if (ocrPending) st.setOcrPending({ ...ocrPending, text: v })
        }}
        onOcrRedo={() => st.setOcrPending(null)}
        onOcrCancel={() => {
          st.setOcrPending(null)
          st.setPickInfo(-1)
        }}
        onOcrOk={ocrOk}
        showAssign={assignOpen}
        onAssignCancel={() => setAssignOpen(false)}
        onAssignConfirm={(assign) => {
          setAssignOpen(false)
          st.setAssign(assign)
          toast('已归案')
          st.close()
        }}
        deleteTarget={deleteTarget}
        onDeleteCancel={() => setDeleteTarget(null)}
        onDeleteConfirm={confirmDelete}
        renaming={renaming}
        onRenamingChange={setRenaming}
        renameMat={renameMat}
        onRenameMatClose={() => setRenameMat(null)}
      />
    </FixedReader>
  )
}

function FixedReader({ children, closing = false }: { children: React.ReactNode; closing?: boolean }) {
  return (
    <div
      className={cn('mp-reader fixed inset-0 z-[80] flex flex-col bg-[#f1f1f3]', closing && 'closing')}
      // 鼠标点按钮不夺焦：否则焦点停在按钮上，随后按空格/回车会重新触发该按钮，导致界面跳动（“闪烁”）
      onMouseDown={(e) => {
        const t = e.target as HTMLElement
        if (t && t.closest && t.closest('button')) e.preventDefault()
      }}
    >
      {children}
    </div>
  )
}
