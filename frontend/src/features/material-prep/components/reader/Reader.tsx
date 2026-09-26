import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useReader } from '../../store'
import { countUnclassified, matLabel, resetSegments } from '../../draft'
import { useMediaQuery } from '../../hooks/use-media'
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
import { ZOOM_MAX, ZOOM_MIN, ZOOM_STEP } from './ui'
import type { PageKey } from '../../types'
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
  const [focusedSeg, setFocusedSeg] = useState(0)
  const [showAssign, setShowAssign] = useState(false)
  const [renaming, setRenaming] = useState(false)
  const [railOpen, setRailOpen] = useState(false)
  const [metaOpen, setMetaOpen] = useState(false)
  // 待确认删除的页（破坏性操作必须先经 AlertDialog 二次确认）
  const [deleteTarget, setDeleteTarget] = useState<PageKey[] | null>(null)
  const addInputRef = useRef<HTMLInputElement>(null)
  const narrow = useMediaQuery('(max-width:1100px)')
  const [flowWrapRef, flowWrapW] = useElementWidth<HTMLDivElement>()
  const { pickPage, onOcrBox, ocrOk } = useReaderOcr()
  const autoSplit = useAutoSplit()

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
    setFocusedSeg(0)
    setRailOpen(false)
    setMetaOpen(false)
    setShowAssign(false)
  }, [openId])

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
  const metaOps = useMemo(() => buildMetaOps(st.update), [st.update])

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
          <p className="text-destructive">{useReader.getState().error}</p>
          <Button onClick={close}>返回</Button>
        </div>
      </FixedReader>
    )
  }

  const unclassified = countUnclassified(draft)
  const allClassified = draft.segs.length > 0 && unclassified === 0
  const pages = draft.mats.reduce((s, m) => s + m.pages, 0)
  const selDetail = selDetailOf(draft, selPages)

  const focusSeg = (si: number) => {
    setFocusedSeg(si)
    requestAnimationFrame(() => {
      document.getElementById(`seg-${si}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  const onToggleSel = (mi: number, p: number, shift: boolean) => st.toggleSel(mi, p, shift)

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

  const zoomIn = () => st.setZoom(Math.min(ZOOM_MAX, +(zoom + ZOOM_STEP).toFixed(2)))
  const zoomOut = () => st.setZoom(Math.max(ZOOM_MIN, +(zoom - ZOOM_STEP).toFixed(2)))
  const zoomVal = Math.round(zoom * 100)

  const ocrFrom = ocrPending ? `${matLabel(draft.mats, ocrPending.mi)} P${ocrPending.p}` : ''
  const ocrTo = pickInfo >= 0 && draft.infos[pickInfo] ? draft.infos[pickInfo].k : ''
  const hintField = pickInfo >= 0 && draft.infos[pickInfo] ? draft.infos[pickInfo].k : ''

  const onComplete = () => {
    if (!allClassified) {
      const first = draft.segs.findIndex((s) => !s.t)
      if (first >= 0) focusSeg(first)
      toast.info('还有未归类的段，先点段头的类型胶囊选一下')
      return
    }
    st.update((d) => ({ ...d, segs: d.segs.map((s) => ({ ...s, done: true })) }))
    toast.success(`拆分与归类完成 —— 共 ${draft.segs.length} 份材料`)
  }

  const onResetSegments = () => {
    st.update((d) => resetSegments(d))
    focusSeg(0)
    toast('已恢复初始分段 —— 每个源文件各一份')
  }

  const onReject = () => {
    st.setStatus('filed')
    toast('已归档留痕，未建案')
    st.close()
  }

  const confirmDelete = () => {
    if (deleteTarget?.length) {
      st.deleteSelected(deleteTarget)
      toast(`已删除 ${deleteTarget.length} 页 —— 从材料拆分中移除`)
    }
    setDeleteTarget(null)
  }

  return (
    <FixedReader closing={closing}>
      <ReaderTopBar
        title={detail.subject || '材料包'}
        subtitle={`${draft.mats.length} 个源文件 · ${pages} 页 · ${draft.segs.length} 份材料 · ${unclassified} 段未归类`}
        allClassified={allClassified}
        onBack={close}
        onReject={onReject}
        onAssign={() => setShowAssign(true)}
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
      {(pickInfo >= 0 || selMode) && <HintBar mode={pickInfo >= 0 ? 'pick' : 'sel'} field={hintField} />}

      {/* 三栏主体 */}
      <div className="relative flex min-h-0 flex-1 bg-[#f1f1f3]">
        {narrow && (railOpen || metaOpen) && (
          <div
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
              const m = draft.mats[mi]
              const name = prompt('源文件名', m.customName || m.n)
              if (name) st.renameMatInDraft(mi, name)
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
        ocrTo={ocrTo}
        onOcrText={(v) => {
          if (ocrPending) st.setOcrPending({ ...ocrPending, text: v })
        }}
        onOcrRedo={() => st.setOcrPending(null)}
        onOcrCancel={() => {
          st.setOcrPending(null)
          st.setPickInfo(-1)
        }}
        onOcrOk={ocrOk}
        showAssign={showAssign}
        onAssignCancel={() => setShowAssign(false)}
        onAssignConfirm={(assign) => {
          setShowAssign(false)
          st.setAssign(assign)
          toast('已归案')
          st.close()
        }}
        deleteTarget={deleteTarget}
        onDeleteCancel={() => setDeleteTarget(null)}
        onDeleteConfirm={confirmDelete}
        renaming={renaming}
        onRenamingChange={setRenaming}
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
