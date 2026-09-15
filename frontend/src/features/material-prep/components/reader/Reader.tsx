import { useEffect, useRef, useState } from 'react'
import {
  ArrowLeft,
  CheckCircle2,
  FolderCheck,
  Loader2,
  Minus,
  Plus,
  ThumbsDown,
  X,
} from 'lucide-react'
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
  setInfoSource,
  setInfoValue,
  setSegmentType,
  splitSegment,
} from '../../draft'
import { canvasToBlob, imageRegionBlob, loadPdfDocument, renderPdfPageRegion } from '@/lib/pdf'
import { fetchAttachmentBytes, ocrImage } from '../../api'
import { Rail } from './Rail'
import { Flow } from './Flow'
import { MetaPanel } from './MetaPanel'
import { OcrPanel } from './OcrPanel'
import { AssignModal } from './AssignModal'
import type { PageRect } from './PageCell'
import type { InfoField } from '../../types'
import { cn } from '@/lib/utils'

function useMediaQuery(query: string): boolean {
  const [match, setMatch] = useState(() => window.matchMedia(query).matches)
  useEffect(() => {
    const mq = window.matchMedia(query)
    const on = () => setMatch(mq.matches)
    mq.addEventListener('change', on)
    return () => mq.removeEventListener('change', on)
  }, [query])
  return match
}

const ZOOM_MIN = 0.6
const ZOOM_MAX = 2.2
const ZOOM_STEP = 0.1

/** 原型 .pbtn：描边按钮，浅色主题下 hover 填充 */
const PBTN =
  'flex h-[30px] flex-none items-center gap-1 rounded-[7px] border border-border bg-transparent px-[13px] text-[12.5px] font-medium text-secondary-foreground transition-colors hover:bg-secondary hover:text-foreground hover:border-zinc-300'
const PBTN_ON = 'bg-secondary text-foreground border-zinc-300'

export function Reader() {
  const { openId, detail, draft, status } = useReader()
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

  const st = useReader.getState()

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

  const pickPage = (mi: number, p: number) => {
    const pi = useReader.getState().pickInfo
    if (pi < 0) return
    const label = `${matLabel(draft.mats, mi)} 第 ${p} 页`
    st.update((d) => setInfoSource(d, pi, label, { mi, p }))
    st.setPickInfo(-1)
    toast.success(`已记来源：${label}`)
  }

  const runOcr = async (mi: number, p: number, rect: PageRect) => {
    const s = useReader.getState()
    const d = s.draft
    if (!d) return
    const m = d.mats[mi]
    if (!m) {
      s.setOcrPending(null)
      return
    }
    s.setOcrPending({ mi, p, rect, text: '', loading: true })
    try {
      let text = ''
      if (m.k === 'pdf') {
        const bytes = await fetchAttachmentBytes(s.openId as number, m.partIndex)
        const doc = await loadPdfDocument(`${s.openId}:${m.partIndex}`, bytes)
        const canvas = await renderPdfPageRegion(doc, p, rect)
        const blob = await canvasToBlob(canvas)
        const res = await ocrImage(blob)
        text = res.blocks.map((b) => b.text).filter(Boolean).join('\n')
      } else if (m.k === 'photo') {
        const bytes = await fetchAttachmentBytes(s.openId as number, m.partIndex)
        const blob = await imageRegionBlob(bytes, rect)
        const res = await ocrImage(blob)
        text = res.blocks.map((b) => b.text).filter(Boolean).join(' ')
      } else {
        toast('Word / Excel 暂不支持逐页取字，已在右栏记下来源页码')
        s.setOcrPending({ mi, p, rect, text: '', loading: false })
        return
      }
      s.setOcrPending({ mi, p, rect, text, loading: false })
    } catch {
      s.setOcrPending({ mi, p, rect, text: '', loading: false })
      toast.error('OCR 识别失败，可重框或手打')
    }
  }

  const onOcrBox = (mi: number, p: number, rect: PageRect) => {
    if (useReader.getState().pickInfo < 0) return
    void runOcr(mi, p, rect)
  }

  const onToggleSel = (mi: number, p: number, shift: boolean) => st.toggleSel(mi, p, shift)

  const ocrOk = () => {
    const s = useReader.getState()
    const pend = s.ocrPending
    if (!pend) return
    const di = s.pickInfo
    s.setOcrPending(null)
    s.setPickInfo(-1)
    if (di < 0) return
    const fieldName = s.draft?.infos[di]?.k || '字段'
    const label = `${matLabel(draft.mats, pend.mi)} 第 ${pend.p} 页`
    s.update((d) => {
      let nd = setInfoSource(d, di, label, { mi: pend.mi, p: pend.p, rect: pend.rect })
      if (pend.text.trim()) nd = setInfoValue(nd, di, pend.text.trim())
      return nd
    })
    toast.success(`已填入「${fieldName}」`)
  }

  // 选页信息
  const selDetail = (() => {
    const idx = selPages.map((o) => pageIndexOf(draft, o.mi, o.p)).filter((i) => i >= 0)
    const flat = flatRefs(draft)
    const involved = new Set(idx.map((i) => flat[i]?.si))
    const cross = involved.size > 1
    return { count: selPages.length, cross }
  })()

  const changeCols = () => {
    const next = cols >= 3 ? 1 : cols + 1
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
    ? cn('fixed inset-y-0 left-0 z-40 w-[268px] overflow-y-auto border-r border-border bg-card transition-transform duration-300', railOpen ? 'translate-x-0 shadow-2xl' : '-translate-x-full')
    : 'flex-none'
  const metaWrapCls = narrow
    ? cn('fixed inset-y-0 right-0 z-40 w-[296px] overflow-y-auto border-l border-border bg-card transition-transform duration-300', metaOpen ? 'translate-x-0 shadow-2xl' : 'translate-x-full')
    : 'flex-none'

  const ocrFrom = ocrPending ? `${matLabel(draft.mats, ocrPending.mi)} P${ocrPending.p}` : ''
  const ocrTo = pickInfo >= 0 && draft.infos[pickInfo] ? draft.infos[pickInfo].k : ''

  return (
    <FixedReader>
      {/* 顶栏 */}
      <div className="flex h-[54px] flex-none items-center gap-3 border-b border-border bg-card px-4">
        <button
          type="button"
          onClick={close}
          className="flex h-8 flex-none items-center gap-1.5 rounded-lg px-2 text-[13px] font-medium text-secondary-foreground hover:bg-secondary"
          title="返回列表 (Esc)"
        >
          <ArrowLeft className="h-4 w-4" />
          材料预处理
        </button>
        <div className="min-w-0">
          <div className="truncate text-[13.5px] font-semibold">{detail.subject || '材料包'}</div>
          <div className="truncate text-[11px] text-muted-foreground">
            {draft.mats.length} 个源文件 · {pages} 页 · {draft.segs.length} 份材料 · {unclassified} 段未归类
          </div>
        </div>
        <div className="ml-auto flex flex-none items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              st.setStatus('filed')
              toast('已归档留痕，未建案')
              st.close()
            }}
          >
            <ThumbsDown className="h-4 w-4" />
            不接
          </Button>
          <Button size="sm" onClick={() => setShowAssign(true)}>
            <FolderCheck className="h-4 w-4" />
            归案
          </Button>
          <button
            type="button"
            onClick={close}
            className="grid h-8 w-8 place-items-center rounded-lg text-secondary-foreground hover:bg-secondary"
            title="关闭"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* 预处理工具条（对齐原型 rd-pre：左进度、右操作，统一 pbtn 描边样式） */}
      <div className="flex h-[56px] flex-none flex-wrap items-center gap-2 border-b border-border bg-card px-4 text-[12.5px]">
        {narrow ? (
          <>
            <button
              type="button"
              onClick={() => {
                setRailOpen((v) => !v)
                setMetaOpen(false)
              }}
              className={cn(PBTN, railOpen && PBTN_ON)}
            >
              材料
            </button>
            <button
              type="button"
              onClick={() => {
                setMetaOpen((v) => !v)
                setRailOpen(false)
              }}
              className={cn(PBTN, metaOpen && PBTN_ON)}
            >
              信息
            </button>
          </>
        ) : null}
        <span className="flex-none rounded-[4px] bg-secondary px-[7px] py-[2px] text-[10px] font-bold uppercase tracking-wide text-secondary-foreground">
          进度
        </span>
        <span className="hidden text-[12px] text-secondary-foreground sm:inline">
          {draft.mats.length} 个源文件 · {pages} 页
        </span>

        <span className="flex-1" />

        <button
          type="button"
          onClick={() => st.toggleSelMode()}
          title="选页模式：点一张选中，⇧+点 选区间（或随时 ⌘/Ctrl+点）"
          className={cn(PBTN, selMode && PBTN_ON)}
        >
          选页
        </button>
        <button
          type="button"
          onClick={() => addInputRef.current?.click()}
          title="点这里选文件，或把文件直接拖到这儿"
          className={PBTN}
        >
          <Plus className="h-3.5 w-3.5" />
          + 追加材料
        </button>

        <span className="h-4 w-px bg-border" />

        <button type="button" onClick={zoomOut} title="缩小画布" className={cn(PBTN, 'w-[30px] justify-center px-0')}>
          <Minus className="h-3.5 w-3.5" />
        </button>
        <button
          type="button"
          onClick={() => st.setZoom(1)}
          title="点击回到 100%"
          className={cn(PBTN, 'min-w-[52px] justify-center px-[8px] tabular-nums')}
        >
          {zoomVal}%
        </button>
        <button type="button" onClick={zoomIn} title="放大画布" className={cn(PBTN, 'w-[30px] justify-center px-0')}>
          <Plus className="h-3.5 w-3.5" />
        </button>

        <button
          type="button"
          onClick={changeCols}
          title="并排列数"
          className={cn(PBTN, 'tabular-nums')}
        >
          列数：{cols}
        </button>

        <span className="h-4 w-px bg-border" />

        <button
          type="button"
          onClick={() => {
            void (async () => {
              st.update((d) => resetSegments(d))
              focusSeg(0)
              toast('已恢复初始分段 —— 每个源文件各一份')
            })()
          }}
          className={PBTN}
        >
          恢复初始分段
        </button>
        <Button
          size="sm"
          className="ml-1"
          onClick={() => {
            if (!allClassified) {
              const first = draft.segs.findIndex((s) => !s.t)
              if (first >= 0) focusSeg(first)
              toast.info('还有未归类的段，先点段头的类型胶囊选一下')
              return
            }
            st.update((d) => ({ ...d, segs: d.segs.map((s) => ({ ...s, done: true })) }))
            toast.success(`拆分与归类完成 —— 共 ${draft.segs.length} 份材料`)
          }}
        >
          <CheckCircle2 className="h-4 w-4" />
          完成拆分与归类
        </Button>
      </div>

      {/* 三栏主体 */}
      <div className="relative flex min-h-0 flex-1 bg-background">
        {narrow && (railOpen || metaOpen) && (
          <div
            className="fixed inset-0 z-30 bg-black/20"
            onClick={() => {
              setRailOpen(false)
              setMetaOpen(false)
            }}
          />
        )}

        {pickInfo >= 0 && (
          <div className="pointer-events-none fixed inset-x-0 top-[100px] z-20 flex justify-center">
            <span className="mt-2 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-[12px] text-amber-700 shadow-sm">
              给「{draft.infos[pickInfo]?.k || '字段'}」取字：页上按住拖一个框 → RapidOCR 识别；只点一下则只记页码
            </span>
          </div>
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

        <div className="relative min-w-0 flex-1 overflow-y-auto">
          <Flow
            draft={draft}
            messageId={openId}
            pickInfo={pickInfo}
            focusedSeg={focusedSeg}
            zoom={zoom}
            cols={narrow ? 1 : cols}
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
        <div className="fixed bottom-[62px] left-1/2 z-[60] flex -translate-x-1/2 items-center gap-3 rounded-xl border border-border bg-card px-4 py-2 shadow-2xl">
          <span className="text-[13px] font-medium tabular-nums">{selDetail.count} 页</span>
          <span className="text-[12px] text-muted-foreground">{selDetail.cross ? '来自多份材料，将合并为一份' : '来自同一份，将独立成一页新材料'}</span>
          <button type="button" onClick={() => st.clearSel()} className="text-[12px] text-secondary-foreground hover:underline">
            取消选择
          </button>
          <button
            type="button"
            onClick={() => st.applySel()}
            className="rounded-md bg-zinc-900 px-3 py-1.5 text-[12.5px] font-medium text-white hover:bg-zinc-700"
          >
            {selDetail.cross ? '合并为一份材料' : '独立成一份材料'}
          </button>
        </div>
      )}

      {/* 底栏：键位提示 + 进度 */}
      <div className="flex h-[42px] flex-none items-center gap-3 border-t border-border bg-card px-4 text-[12px] text-muted-foreground">
        <span>点页间「在此切开」 = 切开</span>
        <span className="hidden sm:inline">
          <b>⌘</b> 点页 选页 · <b>⌘⇧</b> 选区间 · <b>S</b> 合并
        </span>
        <span className="ml-auto flex items-center gap-1.5">
          {allClassified ? (
            <>
              <CheckCircle2 className="h-4 w-4 text-green-600" />
              <span className="text-green-700">全部已归类，可以归案了</span>
            </>
          ) : (
            <span className="text-amber-700">还有 {unclassified} 段没归类</span>
          )}
          <span className="mx-1 h-3 w-px bg-zinc-300" />
          <span>Esc 逐级退出</span>
        </span>
      </div>

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

function FixedReader({ children }: { children: React.ReactNode }) {
  return <div className="fixed inset-0 z-[80] flex flex-col bg-background">{children}</div>
}
