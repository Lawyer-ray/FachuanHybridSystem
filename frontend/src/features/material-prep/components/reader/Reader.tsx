import { useEffect, useRef, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useReader } from '../../store'
import {
  addInfoField,
  countUnclassified,
  flatRefs,
  matLabel,
  mergeSegment,
  pageIndexOf,
  removeInfoField,
  renameSegment,
  resetSegments,
  setInfoValue,
  setSegmentType,
  splitSegment,
} from '../../draft'
import { useMediaQuery } from '../../hooks/use-media'
import { ReaderTopBar } from './ReaderTopBar'
import { ReaderToolbar } from './ReaderToolbar'
import { HintBar } from './HintBar'
import { SelectionBar } from './SelectionBar'
import { KeyHintsBar } from './KeyHintsBar'
import { Rail } from './Rail'
import { Flow } from './Flow'
import { MetaPanel } from './MetaPanel'
import { OcrPanel } from './OcrPanel'
import { AssignModal } from './AssignModal'
import { useReaderOcr } from './use-ocr'
import { useElementWidth } from '../../hooks/use-element-width'
import { COL_MIN_W, COL_GAP } from './Flow'
import { ZOOM_MAX, ZOOM_MIN, ZOOM_STEP } from './ui'
import type { InfoField } from '../../types'
import { cn } from '@/lib/utils'

export function Reader() {
  const { openId, detail, draft, status, closing } = useReader()
  const pickInfo = useReader((s) => s.pickInfo)
  const zoom = useReader((s) => s.zoom)
  const cols = useReader((s) => s.cols)
  const selMode = useReader((s) => s.selMode)
  const selPages = useReader((s) => s.selPages)
  const ocrPending = useReader((s) => s.ocrPending)
  const [focusedSeg, setFocusedSeg] = useState(0)
  const [showAssign, setShowAssign] = useState(false)
  const [railOpen, setRailOpen] = useState(false)
  const [metaOpen, setMetaOpen] = useState(false)
  const addInputRef = useRef<HTMLInputElement>(null)
  const narrow = useMediaQuery('(max-width:1100px)')
  const [flowWrapRef, flowWrapW] = useElementWidth<HTMLDivElement>()
  const { pickPage, onOcrBox, ocrOk } = useReaderOcr()

  const st = useReader.getState()

  // 当前窗口最多能并排几列（每列至少 COL_MIN_W，与 Flow 内 maxColsAllowed 同一口径）
  const maxColsAllowed = Math.max(1, Math.floor((flowWrapW + COL_GAP) / (COL_MIN_W + COL_GAP)))
  const effCols = Math.max(1, Math.min(cols, maxColsAllowed))

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

  // 全局键位：Esc 逐级退出，S 合并选中页
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement
      if (t && t.closest && t.closest('input, textarea, select')) return
      const s = useReader.getState()
      if (e.key === 'Escape') {
        e.preventDefault()
        if (s.ocrPending) {
          s.setOcrPending(null)
          s.setPickInfo(-1)
        } else if (s.selMode) {
          s.clearSel()
          s.toggleSelMode()
        } else if (s.selPages.length) {
          s.clearSel()
        } else if (s.pickInfo >= 0) {
          s.setPickInfo(-1)
        } else {
          s.close()
        }
        return
      }
      if ((e.key === 's' || e.key === 'S') && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) {
        if (s.selPages.length) {
          e.preventDefault()
          s.applySel()
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

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

  const focusSeg = (si: number) => {
    setFocusedSeg(si)
    requestAnimationFrame(() => {
      document.getElementById(`seg-${si}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }

  const onToggleSel = (mi: number, p: number, shift: boolean) => st.toggleSel(mi, p, shift)

  // 选页信息
  const selDetail = (() => {
    const idx = selPages.map((o) => pageIndexOf(draft, o.mi, o.p)).filter((i) => i >= 0)
    const flat = flatRefs(draft)
    const involved = new Set(idx.map((i) => flat[i]?.si))
    const cross = involved.size > 1
    return { count: selPages.length, cross }
  })()

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

  const railWrapCls = narrow
    ? cn(
        'fixed inset-y-0 left-0 z-40 w-[268px] overflow-y-auto border-r border-border bg-card transition-transform duration-300',
        railOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full',
      )
    : 'h-full flex-none'
  const metaWrapCls = narrow
    ? cn(
        'fixed inset-y-0 right-0 z-40 w-[296px] overflow-y-auto border-l border-border bg-card transition-transform duration-300',
        metaOpen ? 'translate-x-0 shadow-2xl' : 'translate-x-full',
      )
    : 'h-full flex-none'

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
            onOp={{
              setSegType: (si, t) => st.update((d) => setSegmentType(d, si, t)),
              renameSeg: (si, name) => st.update((d) => renameSegment(d, si, name)),
              mergeSeg: (si) => st.update((d) => mergeSegment(d, si)),
              toggleDone: (si) =>
                st.update((d) => ({ ...d, segs: d.segs.map((s, i) => (i === si ? { ...s, done: !s.done } : s)) })),
              splitSeg: (si, k) => st.update((d) => splitSegment(d, si, k)),
              pickPage,
            }}
            onToggleSel={onToggleSel}
            onOcrBox={onOcrBox}
            onDeletePages={(picked) => {
              const n = st.deleteSelected(picked)
              if (n > 0) toast(`已删除 ${n} 页 —— 从材料拆分中移除`)
            }}
          />
        </div>

        <div className={metaWrapCls}>
          <MetaPanel
            draft={draft}
            pickInfo={pickInfo}
            onSetPickInfo={(i) => st.setPickInfo(i)}
            ops={{
              addInfo: (field: InfoField) => st.update((d) => addInfoField(d, field)),
              removeInfo: (di) => st.update((d) => removeInfoField(d, di)),
              setValue: (di, v) => st.update((d) => setInfoValue(d, di, v)),
            }}
          />
        </div>
      </div>

      {/* 选页汇总条 */}
      {selPages.length > 0 && (
        <SelectionBar count={selDetail.count} cross={selDetail.cross} onClear={() => st.clearSel()} onApply={() => st.applySel()} />
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

      {/* OCR 确认面板 */}
      {ocrPending && (
        <OcrPanel
          pending={ocrPending}
          fromLabel={ocrFrom}
          toLabel={ocrTo}
          onText={(v) => st.setOcrPending({ ...ocrPending, text: v })}
          onRedo={() => st.setOcrPending(null)}
          onCancel={() => {
            st.setOcrPending(null)
            st.setPickInfo(-1)
          }}
          onOk={ocrOk}
        />
      )}

      {/* 归案归属 */}
      {showAssign && (
        <AssignModal
          open
          count={draft.segs.length}
          infos={draft.infos}
          onCancel={() => setShowAssign(false)}
          onConfirm={(assign) => {
            setShowAssign(false)
            st.setAssign(assign)
            toast('已归案')
            st.close()
          }}
        />
      )}
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
