import { useState } from 'react'
import { Plus, Trash2, Link2 } from 'lucide-react'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { FIELD_LIB } from '../../constants'
import { graphicPagesOf } from '../../draft'
import type { DraftState, InfoField, PageQuality } from '../../types'
import type { MetaOps } from './reader-ops'
import { cn } from '@/lib/utils'
import { PartyPicker } from './PartyPicker'
import { SegmentMarkdown } from './SegmentMarkdown'
import { useMetaWidth } from './use-meta-width'

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
  pageQuality = null,
  onGotoPage,
  pickInfo,
  onSetPickInfo,
  ops,
  focusedSeg,
  mdOpen,
  onToggleMdOpen,
  focusedBlockKey,
  onLocateBlock,
  editRequestKey,
  onEditRequestHandled,
  narrow = false,
}: {
  draft: DraftState
  /** 页级质量统计（旧任务没有）：用于正文面板顶部的「本段含图纸」提示 */
  pageQuality?: PageQuality | null
  /** 从质量提示条跳原页（滚到该页 + 滚到该段） */
  onGotoPage?: (si: number, p: number) => void
  pickInfo: number
  onSetPickInfo: (i: number) => void
  ops: MetaOps
  /** 当前聚焦的段（Markdown 面板跟着它走，与左栏高亮同一口径） */
  focusedSeg: number
  mdOpen: boolean
  onToggleMdOpen: () => void
  focusedBlockKey: string | null
  onLocateBlock: (key: string | null) => void
  /** 页面框双击过来的「进入修改」请求（消费后由调用方清空） */
  editRequestKey?: string | null
  onEditRequestHandled?: () => void
  /** 窄屏时右栏是抽屉，宽度由抽屉 CSS 决定，拖拽手柄不渲染 */
  narrow?: boolean
}) {
  const [showLib, setShowLib] = useState(false)
  // 栏宽可拖拽调整，跨会话记在 localStorage（纯显示偏好，不进草稿）
  const metaWidth = useMetaWidth(narrow)
  // 段数会变（切/并/删），focus 可能落在越界下标上；锁定到有效段，避免编辑写到别的段
  const si = Math.min(Math.max(focusedSeg, 0), Math.max(draft.segs.length - 1, 0))
  // armed 记**字段名**而非下标：先 arm 一行、再删掉前面的空值行会让下标整体前移，
  // 按下标比较会让「确认删除」落到别的字段上（误删有内容字段）。f.k 在字段库去重下唯一。
  const [armDel, setArmDel] = useState<string | null>(null)
  const unavailable = new Set(draft.infos.map((f) => f.k))
  const libRest = FIELD_LIB.filter((f) => !unavailable.has(f.k))

  return (
    <aside
      className="relative flex h-full flex-none flex-col gap-3 overflow-y-auto border-l border-border bg-card p-3"
      // 窄屏是抽屉：宽度由抽屉 CSS 固定，不跟随拖拽值（否则会漏出屏幕）
      style={narrow ? undefined : { width: metaWidth.width }}
    >
      {/* 拖拽手柄：贴左缘（右栏靠屏幕右边，把手放右侧不可达）。
          宽 5px 命中区 + 视觉 1px 线，hover/拖拽时显形提示"可以拖" */}
      {!narrow && (
        <div
          role="separator"
          aria-orientation="vertical"
          aria-label="拖动调整右侧栏宽度"
          onPointerDown={metaWidth.onPointerDown}
          onPointerMove={metaWidth.onPointerMove}
          onPointerUp={metaWidth.endDrag}
          onPointerCancel={metaWidth.endDrag}
          className="group absolute inset-y-0 -left-[3px] z-10 w-[7px] cursor-col-resize touch-none select-none"
        >
          <div className="absolute inset-y-0 left-[3px] w-px bg-transparent transition-colors group-hover:bg-sky-400 group-active:bg-sky-500" />
        </div>
      )}

      {/* Markdown 正文：与材料信息同栏并排，滚动互不干扰。
          放在字段卡之前——先看机器读到了什么，再决定填哪些字段。 */}
      <SegmentMarkdown
        seg={draft.segs[si] ?? null}
        open={mdOpen}
        onToggleOpen={onToggleMdOpen}
        focusedBlockKey={focusedBlockKey}
        onLocateBlock={onLocateBlock}
        editRequestKey={editRequestKey}
        onEditRequestHandled={onEditRequestHandled}
        onEditMarkdown={(md) => ops.editMarkdown(si, md)}
        onEditBlock={(key, text) => ops.editBlock(si, key, text)}
        onRemoveBlock={(key) => ops.removeBlock(si, key)}
        graphicPages={graphicPagesOf(draft.segs[si], pageQuality)}
        onGotoPage={onGotoPage ? (p) => onGotoPage(si, p) : undefined}
      />

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
