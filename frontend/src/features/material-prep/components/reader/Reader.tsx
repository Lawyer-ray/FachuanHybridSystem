import { useEffect, useState } from 'react'
import { ArrowLeft, CheckCircle2, FolderCheck, Loader2, RotateCcw, ThumbsDown, X } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { useReader } from '../../store'
import {
  mergeSegment,
  renameSegment,
  resetSegments,
  setInfoSource,
  setInfoValue,
  setSegmentType,
  splitSegment,
  addInfoField,
  removeInfoField,
  countUnclassified,
  matLabel,
} from '../../draft'
import { Rail } from './Rail'
import { Flow } from './Flow'
import { MetaPanel } from './MetaPanel'
import type { InfoField } from '../../types'

export function Reader() {
  const { openId, detail, draft, status, pickInfo } = useReader()
  const [focusedSeg, setFocusedSeg] = useState(0)

  useEffect(() => {
    setFocusedSeg(0)
  }, [openId])

  const st = useReader.getState()

  // 全局 Esc：先取消标来源，再关阅读器
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return
      const t = e.target as HTMLElement
      if (t && t.closest && t.closest('input, textarea, select')) return
      e.preventDefault()
      const s = useReader.getState()
      if (s.pickInfo >= 0) s.setPickInfo(-1)
      else s.close()
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
          <p className="text-destructive">打开失败</p>
          <Button onClick={close}>返回</Button>
        </div>
      </FixedReader>
    )
  }

  const unclassified = countUnclassified(draft)
  const allClassified = draft.segs.length > 0 && unclassified === 0

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
    useReader.getState().update((d) => setInfoSource(d, pi, label, { mi, p }))
    useReader.getState().setPickInfo(-1)
    toast.success(`已记来源：${label}`)
  }

  return (
    <FixedReader>
      {/* 顶栏 */}
      <div className="flex h-[54px] flex-none items-center gap-3 border-b border-border bg-card px-4">
        <button
          type="button"
          onClick={close}
          className="grid h-8 w-8 flex-none place-items-center rounded-lg text-secondary-foreground hover:bg-secondary"
          title="返回列表 (Esc)"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="min-w-0">
          <div className="truncate text-[13.5px] font-semibold">{detail.subject || '材料包'}</div>
          <div className="truncate text-[11px] text-muted-foreground">
            {draft.mats.length} 个源文件 · {draft.segs.length} 份材料 · {unclassified} 段未归类
          </div>
        </div>
        <div className="ml-auto flex flex-none items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              st.update((d) => resetSegments(d))
              focusSeg(0)
              toast('已恢复初始分段 —— 每个源文件各一份')
            }}
          >
            <RotateCcw className="h-4 w-4" />
            恢复初始分段
          </Button>
          <Button
            size="sm"
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
                  <span className="h-4 w-px bg-border" />
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => toast.info('「不接」属于办案流程，尚未接入，后续再做')}
                  >
                    <ThumbsDown className="h-4 w-4" />
                    不接
                  </Button>
                  <Button
                    size="sm"
                    onClick={() => toast.info('「归案」需要绑定案件，属办案模块，尚未接入，后续再做')}
                  >
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

      {/* 三栏 */}
      <div className="flex min-h-0 flex-1 bg-background">
        {pickInfo >= 0 && (
          <div className="pointer-events-none fixed inset-x-0 top-[54px] z-30 flex justify-center">
            <span className="mt-2 rounded-full border border-amber-300 bg-amber-50 px-3 py-1 text-[12px] text-amber-700 shadow-sm">
              正在标来源：点一页记页码，Esc 取消
            </span>
          </div>
        )}

        <Rail
          draft={draft}
          onFocusSeg={focusSeg}
          onRenameMat={(mi) => {
            const m = draft.mats[mi]
            const name = prompt('源文件名', m.customName || m.n)
            if (name) useReader.getState().renameMatInDraft(mi, name)
          }}
        />

        <div className="relative min-w-0 flex-1 overflow-y-auto">
          <Flow
            draft={draft}
            messageId={openId}
            pickInfo={pickInfo}
            focusedSeg={focusedSeg}
            onOp={{
              setSegType: (si, t) => st.update((d) => setSegmentType(d, si, t)),
              renameSeg: (si, name) => st.update((d) => renameSegment(d, si, name)),
              mergeSeg: (si) => st.update((d) => mergeSegment(d, si)),
              toggleDone: (si) =>
                st.update((d) => ({ ...d, segs: d.segs.map((s, i) => (i === si ? { ...s, done: !s.done } : s)) })),
              splitSeg: (si, k) => st.update((d) => splitSegment(d, si, k)),
              pickPage,
            }}
          />
        </div>

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

      {/* 底栏 */}
      <div className="flex h-[46px] flex-none items-center gap-3 border-t border-border bg-card px-4 text-[12.5px]">
        <span className={allClassified ? 'flex items-center gap-1.5 text-green-700' : 'text-amber-700'}>
          {unclassified > 0 ? `还有 ${unclassified} 段没归类 —— 点段头的类型胶囊选一下` : (
            <>
              <CheckCircle2 className="h-4 w-4" /> 全部已归类，可以归案了
            </>
          )}
        </span>
        <span className="ml-auto text-[11px] text-muted-foreground">Esc 关闭阅读器</span>
      </div>
    </FixedReader>
  )
}

function FixedReader({ children }: { children: React.ReactNode }) {
  return <div className="fixed inset-0 z-[80] flex flex-col bg-background">{children}</div>
}
