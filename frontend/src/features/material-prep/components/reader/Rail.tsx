import { FileText, Image, Layers, PencilLine } from 'lucide-react'
import { SEG_COLORS } from '../../constants'
import type { BundleMat, DraftState } from '../../types'
import { countUnclassified, isWholeMat, segMats } from '../../draft'

export function Rail({
  draft,
  onFocusSeg,
  onRenameMat,
}: {
  draft: DraftState
  onFocusSeg: (si: number) => void
  onRenameMat: (mi: number) => void
}) {
  const { mats } = draft
  const unclassified = countUnclassified(draft)

  // 每个素材下挂它的段；跨源段归到「跨源合并」一组
  const groups: { mi: number; segs: number[] }[] = []
  const cross: number[] = []
  draft.segs.forEach((sg, si) => {
    const mis = segMats(sg)
    if (mis.length > 1 || mis.length === 0) {
      cross.push(si)
    } else {
      const g = groups.find((x) => x.mi === mis[0])
      if (g) g.segs.push(si)
      else groups.push({ mi: mis[0], segs: [si] })
    }
  })

  const matIcon = (m: BundleMat) =>
    m.k === 'pdf' ? (
      <FileText className="h-4 w-4" />
    ) : m.k === 'photo' ? (
      <Image className="h-4 w-4" />
    ) : (
      <Layers className="h-4 w-4" />
    )

  return (
    <aside className="flex w-[268px] flex-none flex-col gap-3 overflow-y-auto border-r border-border bg-card p-3">
      <div className="px-1">
        <h4 className="text-sm font-medium">
          材料 <span className="text-xs font-normal text-muted-foreground">{draft.segs.length} 份</span>
        </h4>
        <div className="mt-0.5 text-xs text-secondary-foreground">
          来自 {mats.length} 个源文件 · {unclassified} 段未归类
        </div>
      </div>

      {draft.segs.length === 0 && (
        <p className="px-1 text-xs text-muted-foreground">还没有材料。先点右上角新建材料包。</p>
      )}

      {groups.map(({ mi, segs }) => {
        const m = mats[mi]
        if (!m) return null
        return (
          <div key={mi}>
            <div className="group flex items-center gap-1.5 rounded-md px-1.5 py-1 hover:bg-secondary">
              <span className="text-secondary-foreground">{matIcon(m)}</span>
              <span className="min-w-0 flex-1 truncate text-[13px]">{m.customName || m.n}</span>
              <button
                type="button"
                title="改源文件名字"
                onClick={() => onRenameMat(mi)}
                className="grid h-5 w-5 flex-none place-items-center rounded text-zinc-300 opacity-0 transition group-hover:opacity-100 hover:bg-card hover:text-foreground"
              >
                <PencilLine className="h-3.5 w-3.5" />
              </button>
              <span className="flex-none text-[11px] tabular-nums text-muted-foreground">{m.pages} 页 ↗ {segs.length} 份</span>
            </div>
            <div className="ml-2 mt-0.5 flex flex-col gap-0.5 border-l border-zinc-200 pl-2.5">
              {segs.map((si) => {
                const sg = draft.segs[si]
                const color = SEG_COLORS[si % SEG_COLORS.length]
                const whole = isWholeMat(draft, si)
                return (
                  <button
                    key={si}
                    type="button"
                    onClick={() => onFocusSeg(si)}
                    className="flex items-center gap-1.5 rounded-md px-1.5 py-1 text-left hover:bg-secondary"
                  >
                    <span className="h-2 w-2 flex-none rounded-full" style={{ background: sg.t ? color : 'transparent', border: sg.t ? 'none' : '1px dashed #a1a1aa' }} />
                    <span className="min-w-0 flex-1 truncate text-[13px]">{whole ? '整份' : sg.fn}</span>
                    <span
                      className={
                        sg.t
                          ? 'flex-none rounded-full border border-green-200 bg-green-50 px-1.5 text-[10.5px] text-green-700'
                          : 'flex-none rounded-full border border-amber-200 bg-amber-50 px-1.5 text-[10.5px] text-amber-700'
                      }
                    >
                      {sg.t || '未归类'}
                    </span>
                  </button>
                )
              })}
            </div>
          </div>
        )
      })}

      {cross.length > 0 && (
        <div>
          <div className="flex items-center gap-1.5 px-1.5 py-1 text-[13px] text-secondary-foreground">
            <Layers className="h-4 w-4" />
            <span className="min-w-0 flex-1 truncate">跨源合并</span>
            <span className="text-[11px] tabular-nums text-muted-foreground">{cross.length} 份</span>
          </div>
          <div className="ml-2 mt-0.5 flex flex-col gap-0.5 border-l border-zinc-200 pl-2.5">
            {cross.map((si) => {
              const sg = draft.segs[si]
              return (
                <button
                  key={si}
                  type="button"
                  onClick={() => onFocusSeg(si)}
                  className="flex items-center gap-1.5 rounded-md px-1.5 py-1 text-left hover:bg-secondary"
                >
                  <span className="h-2 w-2 flex-none rounded-full bg-zinc-400" />
                  <span className="min-w-0 flex-1 truncate text-[13px]">{sg.fn}</span>
                  <span
                    className={
                      sg.t
                        ? 'flex-none rounded-full border border-green-200 bg-green-50 px-1.5 text-[10.5px] text-green-700'
                        : 'flex-none rounded-full border border-amber-200 bg-amber-50 px-1.5 text-[10.5px] text-amber-700'
                    }
                  >
                    {sg.t || '未归类'}
                  </span>
                </button>
              )
            })}
          </div>
        </div>
      )}
    </aside>
  )
}
