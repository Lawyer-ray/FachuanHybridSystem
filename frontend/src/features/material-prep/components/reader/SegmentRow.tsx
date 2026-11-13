import { useState } from 'react'
import { Check, Trash2 } from 'lucide-react'

import { cn } from '@/lib/utils'

/**
 * 右栏正文面板的「行」组件：一行正文 + 「没有定位块」时的整段编辑。
 *
 * 从 `SegmentMarkdown` 拆出：那两个组件各自带本地编辑态（草稿文本、输入框生命周期），
 * 与面板本身的展折/定位接线是两件事；合在一起会让面板文件顶到规模软红线。
 */

/** 一行正文：平时是文字（双击定位），编辑态是输入框（失焦/回车保存）。 */
export function BlockRow({
  blockKey,
  text,
  page,
  approx,
  active,
  editing,
  onLocate,
  onRemove,
  onStartEdit,
  onCommitEdit,
  onCancelEdit,
}: {
  blockKey: string
  text: string
  page: number
  approx?: boolean
  active: boolean
  editing: boolean
  onLocate: (key: string | null) => void
  onRemove?: (key: string) => void
  onStartEdit?: (key: string) => void
  onCommitEdit: (text: string) => void
  onCancelEdit: () => void
}) {
  const [draft, setDraft] = useState(text)

  if (editing) {
    // 编辑态：输入框 + **显式的保存/取消按钮**。
    //
    // 不用「失焦即保存」——这一行是法律文书正文，改错了下游 AI 会拿错文本跑，
    // 该由人明确说「我要保存」。失焦保存还有三个实际问题：
    //   ① 界面上没有任何提示，用户不知道"切走"就等于提交；
    //   ② 误点别处（想复制文字、想对照原页）就改了库；
    //   ③ 回车保存会让父级卸载输入框 → 触发 blur → 再提交一次（重复写入）。
    // 回车 / Esc 作为快捷键保留给熟手，但**不再是唯一入口**。
    return (
      <div className="flex flex-col gap-1 rounded border border-sky-300 bg-sky-50/40 p-1">
        <div className="flex items-start gap-1">
          <span className="mt-1 flex-none tabular-nums text-[10.5px] text-muted-foreground">P{page}</span>
          <textarea
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                onCommitEdit(draft)
              }
              if (e.key === 'Escape') onCancelEdit()
            }}
            spellCheck={false}
            rows={Math.min(6, Math.max(2, Math.ceil(draft.length / 38)))}
            className="min-w-0 flex-1 resize-y rounded border border-sky-300 bg-white p-1 font-mono text-[11px] leading-relaxed outline-none focus:ring-1 focus:ring-sky-400"
          />
        </div>
        <div className="flex items-center gap-1.5 pl-5">
          <button
            type="button"
            onClick={() => onCommitEdit(draft)}
            className="flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-0.5 text-[10.5px] font-medium text-white hover:bg-zinc-800"
          >
            <Check className="h-2.5 w-2.5" aria-hidden />
            保存
          </button>
          <button
            type="button"
            onClick={onCancelEdit}
            className="rounded-md border border-border bg-white px-2 py-0.5 text-[10.5px] hover:bg-secondary"
          >
            取消
          </button>
          <span className="ml-auto text-[10px] text-muted-foreground">回车保存 · Esc 取消</span>
        </div>
      </div>
    )
  }

  return (
    <div className="group/row flex items-start gap-0.5">
      <button
        type="button"
        // 双击才定位：单击是阅读时的选中文字动作，不该触发跳转
        onDoubleClick={() => onLocate(active ? null : blockKey)}
        onContextMenu={
          onStartEdit
            ? (e) => {
                e.preventDefault()
                onStartEdit(blockKey)
              }
            : undefined
        }
        title={`第 ${page} 页${approx ? '（整页近似框）' : ''} · 双击定位${onStartEdit ? ' · 右键改这一行' : ''}`}
        className={cn(
          'flex min-w-0 flex-1 items-start gap-1.5 rounded px-1.5 py-1 text-left text-[11px] leading-relaxed transition-colors',
          active ? 'bg-sky-50 text-sky-900 ring-1 ring-sky-300' : 'hover:bg-secondary/60',
        )}
      >
        <span className="flex-none tabular-nums text-muted-foreground">P{page}</span>
        <span className="min-w-0 flex-1 whitespace-pre-wrap break-words">{text || '（空块）'}</span>
      </button>
      {onRemove && (
        <button
          type="button"
          onClick={() => onRemove(blockKey)}
          title="这个定位框画错了：删掉它（不影响正文）"
          aria-label="删除这个定位框"
          className="mt-1 grid h-4 w-4 flex-none place-items-center rounded text-zinc-300 opacity-0 transition-opacity hover:text-destructive focus-visible:opacity-100 group-hover/row:opacity-100 [@media(hover:none)]:opacity-100"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      )}
    </div>
  )
}

/** 没有定位块时的整段编辑（md 存在但后端没给坐标）。 */
export function WholeTextEditor({
  text,
  editing,
  onStartEdit,
  onCommit,
  onCancel,
}: {
  text: string
  editing: boolean
  onStartEdit?: () => void
  onCommit: (v: string) => void
  onCancel: () => void
}) {
  const [draft, setDraft] = useState(text)

  if (editing) {
    return (
      <div className="flex flex-col gap-1">
        <textarea
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Escape') onCancel()
          }}
          spellCheck={false}
          className="max-h-[46vh] min-h-[140px] w-full resize-y overflow-auto rounded-lg border border-sky-300 bg-white p-2 font-mono text-[11px] leading-[1.7] outline-none focus:ring-1 focus:ring-sky-400"
        />
        <div className="flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => onCommit(draft)}
            className="flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-1 text-[11px] font-medium text-white hover:bg-zinc-800"
          >
            <Check className="h-3 w-3" aria-hidden />
            保存
          </button>
          <button
            type="button"
            onClick={onCancel}
            className="rounded-md border border-border px-2 py-1 text-[11px] hover:bg-secondary"
          >
            取消
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="group/whole relative">
      <pre className="max-h-[46vh] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-zinc-200 bg-secondary/40 p-2 text-[11px] leading-[1.7] text-foreground">
        {text}
      </pre>
      {onStartEdit && (
        <button
          type="button"
          onClick={onStartEdit}
          className="absolute right-1 top-1 rounded bg-white/90 px-1.5 py-0.5 text-[10.5px] text-muted-foreground opacity-0 shadow-sm transition-opacity hover:text-foreground group-hover/whole:opacity-100"
        >
          改正文
        </button>
      )}
    </div>
  )
}
