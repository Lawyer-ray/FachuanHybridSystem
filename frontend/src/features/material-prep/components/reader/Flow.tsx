import { Scissors } from 'lucide-react'
import { SEG_COLORS } from '../../constants'
import type { DraftState } from '../../types'
import { PageCell } from './PageCell'
import { SegmentHeader } from './SegmentHeader'

export function Flow({
  draft,
  messageId,
  pickInfo,
  focusedSeg,
  onOp,
}: {
  draft: DraftState
  messageId: number
  pickInfo: number
  focusedSeg: number
  onOp: {
    setSegType: (si: number, t: string) => void
    renameSeg: (si: number, name: string) => void
    mergeSeg: (si: number) => void
    toggleDone: (si: number) => void
    splitSeg: (si: number, k: number) => void
    pickPage: (mi: number, p: number) => void
  }
}) {
  const { segs, mats } = draft

  return (
    <div className="mx-auto flex flex-col gap-5 px-5 py-6" style={{ maxWidth: 920 }}>
      {segs.map((seg, si) => {
        const color = SEG_COLORS[si % SEG_COLORS.length]
        const focused = focusedSeg === si
        return (
          <section
            key={si}
            id={`seg-${si}`}
            className={`flex flex-col gap-1.5 transition-opacity ${focused ? '' : 'opacity-95'}`}
          >
            <SegmentHeader
              seg={seg}
              si={si}
              draft={draft}
              color={color}
              onSetType={(t) => onOp.setSegType(si, t)}
              onRename={(name) => onOp.renameSeg(si, name)}
              onMerge={() => onOp.mergeSeg(si)}
              onToggleDone={() => onOp.toggleDone(si)}
            />

            <div className="flex flex-col items-center gap-1.5">
              {seg.refs.map((ref, ri) => {
                const mat = mats[ref.mi]
                if (!mat) return null
                const firstPageOfSeg = ri === 0
                return (
                  <div key={ref.mi + '-' + ref.p} className="flex w-full flex-col items-center gap-1.5">
                    {firstPageOfSeg && (
                      <div className="w-full rounded-[7px] border border-dashed border-zinc-300 py-1 text-center text-[11px] text-muted-foreground">
                        段开始 · {mat.customName || mat.n}
                      </div>
                    )}
                    <PageCell
                      messageId={messageId}
                      mi={ref.mi}
                      p={ref.p}
                      mat={mat}
                      focused={pickInfo >= 0 && false}
                      onPickPage={pickInfo >= 0 ? onOp.pickPage : undefined}
                    />
                    {ri < seg.refs.length - 1 && (
                      <button
                        type="button"
                        title="在此切开：把这段从这一页后面分成两份"
                        onClick={() => onOp.splitSeg(si, ri)}
                        className="group flex h-[30px] w-full items-center justify-center gap-2 rounded-[6px] border border-dashed border-zinc-300 text-[12px] text-muted-foreground transition-all hover:border-amber-400 hover:bg-amber-50 hover:text-amber-700"
                      >
                        <span className="pointer-events-none flex items-center gap-2">
                          <Scissors className="h-3.5 w-3.5" />
                          在此切开
                        </span>
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          </section>
        )
      })}
    </div>
  )
}
