import { useState } from 'react'
import { Plus, Trash2, Link2 } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { FIELD_LIB } from '../../constants'
import type { DraftState, InfoField } from '../../types'
import type { MetaOps } from './reader-ops'
import { cn } from '@/lib/utils'
import { PartyPicker } from './PartyPicker'

/** 字段的 placeholder：把「多个用、分隔」这类提示并进去，不再在标签旁常驻一行小字 */
function placeholderOf(f: InfoField): string | undefined {
  if (!f.hint) return f.ph
  return f.ph ? `${f.ph}，${f.hint}` : f.hint
}

/** 右栏「材料信息」：便签式字段卡。
 *
 *  标签旁只留两个图标（标来源 / 删除），删除悬停才显形；「便签，不是表单」那句说明
 *  只在一条都没记时作为空态出现，记了第一条它就该让位。 */
export function MetaPanel({
  draft,
  pickInfo,
  onSetPickInfo,
  ops,
}: {
  draft: DraftState
  pickInfo: number
  onSetPickInfo: (i: number) => void
  ops: MetaOps
}) {
  const [showLib, setShowLib] = useState(false)
  // armed 记**字段名**而非下标：先 arm 一行、再删掉前面的空值行会让下标整体前移，
  // 按下标比较会让「确认删除」落到别的字段上（误删有内容字段）。f.k 在字段库去重下唯一。
  const [armDel, setArmDel] = useState<string | null>(null)
  const unavailable = new Set(draft.infos.map((f) => f.k))
  const libRest = FIELD_LIB.filter((f) => !unavailable.has(f.k))

  return (
    <aside className="flex h-full w-[256px] flex-none flex-col gap-3 overflow-y-auto border-l border-border bg-card p-3 xl:w-[296px]">
      <h4 className="px-1 text-sm font-medium">材料信息</h4>

      {draft.infos.length === 0 && (
        <p className="px-1 text-[11.5px] leading-relaxed text-muted-foreground">
          便签，不是表单。想记就记，一条不记也能继续。
        </p>
      )}

      {draft.infos.map((f, di) => {
        const picking = pickInfo === di
        const armed = armDel === f.k
        return (
          <div key={f.k} className="group flex flex-col gap-1.5 rounded-lg border border-zinc-200 bg-card p-2.5">
            <div className="flex items-center gap-1">
              <span className="text-[12.5px] font-medium">{f.k}</span>
              <span className="ml-auto" />
              {/* 标来源：图标即入口；取字态下亮琥珀，顶部提示条负责解释怎么做 */}
              <button
                type="button"
                onClick={() => onSetPickInfo(picking ? -1 : di)}
                title={picking ? '取字中：在页面上点一页或拖一个框；再点取消' : '标来源：在页面上点一页 / 拖框取字'}
                aria-label={picking ? '取消标来源' : '标来源'}
                aria-pressed={picking}
                className={cn(
                  'grid h-5 w-5 place-items-center rounded transition-colors',
                  picking ? 'bg-amber-100 text-amber-700' : 'text-zinc-400 hover:bg-secondary hover:text-foreground',
                )}
              >
                <Link2 className="h-3.5 w-3.5" />
              </button>
              {/* 删除：悬停 / 聚焦 / 已 arm 才显形；触屏无 hover 常显 */}
              <button
                type="button"
                title="删除这个字段"
                aria-label="删除这个字段"
                onClick={() => {
                  if (armed) {
                    ops.removeInfo(di)
                    setArmDel(null)
                  } else if (f.v) {
                    setArmDel(f.k)
                  } else {
                    ops.removeInfo(di)
                  }
                }}
                onBlur={() => setArmDel(null)}
                className={cn(
                  'grid h-5 w-5 place-items-center rounded text-zinc-300 opacity-0 transition-opacity hover:text-destructive focus-visible:opacity-100 group-hover:opacity-100 [@media(hover:none)]:opacity-100',
                  armed && 'bg-destructive/10 text-destructive opacity-100',
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
                placeholder={placeholderOf(f)}
                value={f.v}
                onChange={(e) => ops.setValue(di, e.target.value)}
                className="resize-none text-[13px]"
              />
            ) : f.k === '委托人' || f.k === '对方当事人' || f.k === '受益人' ? (
              <PartyPicker
                value={f.v}
                onChange={(v) => ops.setValue(di, v)}
                placeholder={placeholderOf(f)}
                isOurClient={f.k !== '对方当事人'}
              />
            ) : (
              <Input
                placeholder={placeholderOf(f)}
                value={f.v}
                onChange={(e) => ops.setValue(di, e.target.value)}
                className="h-8 text-[13px]"
              />
            )}

            {f.src && (
              <span className="truncate text-[11px] tabular-nums text-muted-foreground" title={`来源：${f.src}`}>
                来源 {f.src}
              </span>
            )}
          </div>
        )
      })}

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
