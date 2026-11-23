import { useState } from 'react'
import { Check, Trash2 } from 'lucide-react'

import { cn } from '@/lib/utils'
import { rectPrecisionOf, type RectPrecision } from '../../types'

/**
 * 右栏正文面板的「行」组件：一行正文（双击定位原页、右键就地改）。
 *
 * 从 `SegmentMarkdown` 拆出：它自带本地编辑态（草稿文本、输入框生命周期），
 * 与面板本身的展折/定位接线是两件事；合在一起会让面板文件顶到规模软红线。
 * 整段编辑在 `SegmentMarkdownView`（渲染 / 源码 / 编辑三态）。
 */

/**
 * 定位框可信度的人话（tooltip 用）。
 *
 * 以前只用 `approx` 判「整页近似框」，于是**所有**均分推算的表格块（`precision=cell`）
 * 都被说成「整页近似框」——这是两种完全不同的不可信程度：整表一个框（坐标基本无意义）
 * 与格子/列有偏差（八九不离十）。按 precision 分档说之后：
 *   grid  → 已按原表实测格子定位（可信）
 *   cell  → 表格均分推算，可能半格偏差（要去核）
 *   page  → 整表近似框（坐标无意义）
 *   exact → 不加任何限定语（引擎原样返回，说了反而像在打折扣）
 *
 * 缺 `precision` 的旧数据退化看 `approx`（走 `rectPrecisionOf`，与画框同一条判定链，
 * 避免「框画成虚线、文案说是精确」这类自相矛盾）。
 */
function precisionHintOf(h: { approx?: boolean; precision?: RectPrecision }): string {
  const precision = h.precision ?? rectPrecisionOf(h)
  if (precision === 'grid') return '已按原表实测格子定位'
  if (precision === 'cell') return '表格均分推算，可能半格偏差'
  if (precision === 'page') return '整表近似框'
  return ''
}

/**
 * 编辑态的一行：输入框 + 显式保存/取消。
 *
 * 草稿归它自己（**挂载时**按 `initialText` 定初值），不是留在 BlockRow 里用 effect 同步：
 * 那个写法要先渲染一轮旧文本、effect 跑完才换成种子文本，输入框会先闪一下原文。
 * 代价是它必须随种子文本重新挂载，所以由 BlockRow 给 key（见那里的注释）。
 */
function BlockEditRow({
  page,
  initialText,
  onCommitEdit,
  onCancelEdit,
}: {
  page: number
  /** 进入编辑态时的初值：种子文本（有的话）或本行原文 */
  initialText: string
  onCommitEdit: (text: string) => void
  onCancelEdit: () => void
}) {
  const [draft, setDraft] = useState(initialText)

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

/** 一行正文：平时是文字（双击定位），编辑态是输入框（保存/取消）。 */
export function BlockRow({
  blockKey,
  text,
  page,
  approx,
  precision,
  active,
  editing,
  onLocate,
  onRemove,
  onStartEdit,
  onCommitEdit,
  onCancelEdit,
  seedText = null,
}: {
  blockKey: string
  text: string
  page: number
  /** 定位框是否「整页近似」（旧语义，只在缺 `precision` 时兜底用） */
  approx?: boolean
  /**
   * 定位框精度（后端 `PositionedRectOut.precision` 透传）。
   *
   * 与 `approx` 并存而不是替换它：旧草稿 / 旧任务产物里没有 precision，
   * 那时只能靠 approx 判；两条路都收进 `precisionHintOf`，判定口径只有一处。
   */
  precision?: RectPrecision
  active: boolean
  editing: boolean
  onLocate: (key: string | null) => void
  onRemove?: (key: string) => void
  onStartEdit?: (key: string) => void
  onCommitEdit: (text: string) => void
  onCancelEdit: () => void
  /**
   * 进入编辑态时预填的文本（缺省用本行原文）。
   *
   * 用于「两个引擎都不对」的场景：律师点分歧里的「采用」时，把该引擎的完整文本
   * 预填进来，他只需要改那几个错字，而不是对着 60+ 字的一行从零手打。
   */
  seedText?: string | null
}) {
  if (editing) {
    // 编辑态下沉到 BlockEditRow：草稿是**它自己挂载时**按种子文本定的初值。
    //
    // key 写种子文本：同一个 BlockRow 实例在不同次编辑之间是复用的，而「点采用」
    // 可能在编辑中把种子文本换成另一侧引擎的全文——key 变了才重新挂载，草稿才会
    // 回到新的种子文本；同一种子文本下的父级重渲染则不会碰用户已经打的字。
    return (
      <BlockEditRow
        key={seedText ?? ''}
        page={page}
        initialText={seedText ?? text}
        onCommitEdit={onCommitEdit}
        onCancelEdit={onCancelEdit}
      />
    )
  }

  // 定位可信度的限定语：空串（exact）时不出括号，tooltip 保持短
  const hint = precisionHintOf({ approx, precision })

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
        title={`第 ${page} 页${hint ? `（${hint}）` : ''} · 双击定位${onStartEdit ? ' · 右键改这一行' : ''}`}
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
