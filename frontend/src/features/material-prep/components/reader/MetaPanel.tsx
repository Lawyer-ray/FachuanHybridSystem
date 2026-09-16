import { useState } from 'react'
import { Plus, Trash2, Link2 } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { FIELD_LIB } from '../../constants'
import type { DraftState, InfoField } from '../../types'
import { cn } from '@/lib/utils'

export function MetaPanel({
  draft,
  pickInfo,
  onSetPickInfo,
  ops,
}: {
  draft: DraftState
  pickInfo: number
  onSetPickInfo: (i: number) => void
  ops: {
    addInfo: (field: InfoField) => void
    removeInfo: (di: number) => void
    setValue: (di: number, v: string) => void
  }
}) {
  const [showLib, setShowLib] = useState(false)
  const [armDel, setArmDel] = useState<number>(-1)
  const unavailable = new Set(draft.infos.map((f) => f.k))
  const libRest = FIELD_LIB.filter((f) => !unavailable.has(f.k))

  return (
    <aside className="flex h-full w-[256px] flex-none flex-col gap-3 overflow-y-auto border-l border-border bg-card p-3 xl:w-[296px]">
      <div className="px-1">
        <h4 className="flex items-center justify-between text-sm font-medium">
          材料信息
          <span className="text-xs font-normal text-muted-foreground">已记 {draft.infos.filter((f) => f.v).length} 项</span>
        </h4>
        <p className="mt-1 text-[11.5px] leading-relaxed text-muted-foreground">
          便签，不是表单。想记就记，一条不记也能继续。
        </p>
      </div>

      {draft.infos.map((f, di) => (
        <div key={f.k} className="flex flex-col gap-1.5 rounded-lg border border-zinc-200 bg-card p-2.5">
          <div className="flex items-center gap-1">
            <span className="text-[12.5px] font-medium">{f.k}</span>
            {f.hint && <span className="text-[11px] text-muted-foreground">{f.hint}</span>}
            <span className="ml-auto" />
            <button
              type="button"
              title="删除这个字段"
              onClick={() => {
                if (armDel === di) {
                  ops.removeInfo(di)
                  setArmDel(-1)
                } else if (f.v) {
                  setArmDel(di)
                } else {
                  ops.removeInfo(di)
                }
              }}
              onBlur={() => setArmDel(-1)}
              className={cn(
                'grid h-5 w-5 place-items-center rounded text-zinc-300 hover:text-destructive',
                armDel === di && 'bg-destructive/10 text-destructive',
              )}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </button>
          </div>

          {f.opts ? (
            <select
              value={f.v}
              onChange={(e) => ops.setValue(di, e.target.value)}
              className="h-8 rounded-md border border-input bg-background px-2 text-[13px] outline-none"
            >
              <option value="">— 选择 —</option>
              {f.opts.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          ) : f.ta ? (
            <Textarea
              rows={2}
              placeholder={f.ph}
              value={f.v}
              onChange={(e) => ops.setValue(di, e.target.value)}
              className="resize-none text-[13px]"
            />
          ) : (
            <Input
              placeholder={f.ph}
              value={f.v}
              onChange={(e) => ops.setValue(di, e.target.value)}
              className="h-8 text-[13px]"
            />
          )}

          {/* 标来源 */}
          <div className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={() => onSetPickInfo(pickInfo === di ? -1 : di)}
              className={cn(
                'flex items-center gap-1 rounded-full border px-2 py-0.5 text-[11.5px] transition-colors',
                pickInfo === di
                  ? 'border-amber-300 bg-amber-50 text-amber-700'
                  : 'border-border text-secondary-foreground hover:bg-secondary',
              )}
            >
              <Link2 className="h-3 w-3" />
              {pickInfo === di ? '点一页作为来源' : '标来源'}
            </button>
            {f.src && (
              <span className="truncate text-[11px] tabular-nums text-muted-foreground">{f.src}</span>
            )}
          </div>
        </div>
      ))}

      {/* 记一项 */}
      <div className="flex flex-col gap-1">
        <button
          type="button"
          onClick={() => setShowLib((v) => !v)}
          className="flex items-center gap-1 rounded-full border border-dashed border-zinc-300 px-2.5 py-1 text-[12.5px] text-secondary-foreground hover:border-zinc-400 hover:bg-secondary"
        >
          <Plus className="h-3.5 w-3.5" />
          记一项
        </button>
        {showLib && (
          <div className="flex flex-wrap gap-1">
            {libRest.length === 0 && <span className="text-[11px] text-muted-foreground">字段库已用完</span>}
            {libRest.map((f) => (
              <button
                key={f.k}
                type="button"
                onClick={() => {
                  ops.addInfo(f)
                  setShowLib(false)
                }}
                className="rounded-full border border-border bg-card px-2.5 py-0.5 text-[12px] text-secondary-foreground hover:bg-secondary"
              >
                {f.k}
              </button>
            ))}
          </div>
        )}
      </div>
    </aside>
  )
}
