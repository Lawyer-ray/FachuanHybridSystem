import { useState } from 'react'
import { Check, ChevronDown, ChevronRight, FileCode2, Trash2 } from 'lucide-react'

import { blockKeyOf } from '../../draft/block-keys'
import type { Segment } from '../../types'
import { cn } from '@/lib/utils'

/**
 * 右侧栏的「Markdown 正文」面板（云端识别的取字结果）。
 *
 * ## 为什么需要它
 *
 * 自动分段一直在产出 `seg.md`，但此前**没有任何 UI 展示**——只被「识别当事人」
 * 与「推断文本」在后台消费掉。律师看不到机器读出了什么，等于整条识别链路是黑盒。
 *
 * ## 为什么在右栏而不是嵌在每段页面之上
 *
 * 一版曾把它放在段头下方。正文动辄数千字，展开后把这些段落之间的页面全推到
 * 屏幕外，「边看正文边对照原页」反而做不到。右栏与页面流并排常驻，
 * 滚动互不干扰，才是「原文对照」的正确形态。
 *
 * ## 对照靠双击，不靠单击
 *
 * 单击只是选中一行文字（阅读时的自然动作），**双击**才跳转并在原页亮出定位框。
 * 默认状态下页面上的识别框全部按常态显示——不预先高亮任何一条，
 * 否则一进阅读器满屏都是「重点」，反而看不出哪条对应哪里。
 *
 * 高亮是**互斥**的：定位一个块时其余框淡化，只留这一条 + 它的原页位置。
 */
export function SegmentMarkdown({
  seg,
  open,
  onToggleOpen,
  focusedBlockKey,
  onLocateBlock,
  onEditMarkdown,
  onEditBlock,
  onRemoveBlock,
}: {
  seg: Segment | null
  /** 展开态由父级持有（右栏其它块共用同一个折叠开关，避免各自记住状态） */
  open: boolean
  onToggleOpen: () => void
  /** 当前高亮的块 key；null = 不高亮任何框 */
  focusedBlockKey: string | null
  /** 双击某一条 → 滚到原页并高亮该框（传 null 表示取消） */
  onLocateBlock: (key: string | null) => void
  /** 手改正文（识别错字/表格拍平时律师自己修）——没有定位块时的整段编辑 */
  onEditMarkdown?: (md: string) => void
  /** 改某一行（定位块）的文字；同步进 Markdown 正文 */
  onEditBlock?: (key: string, text: string) => void
  /** 删掉一个画错的定位框（只删坐标，不动正文） */
  onRemoveBlock?: (key: string) => void
}) {
  // 正在编辑的那一行的 key；null = 全部只读
  const [editingKey, setEditingKey] = useState<string | null>(null)
  // 没有定位块时的整段编辑开关
  const [editingAll, setEditingAll] = useState(false)

  if (!seg) return null

  // 人工拆分 / 本地 OCR / 旧任务都没有 md：明确说"没有"，而不是渲染空白
  if (!seg.md) {
    if (seg.manual) return null
    return (
      <div className="flex items-start gap-1.5 rounded-lg border border-zinc-200 bg-secondary/40 px-2.5 py-1.5 text-[11px] leading-relaxed text-muted-foreground">
        <FileCode2 className="mt-0.5 h-3 w-3 flex-none opacity-60" aria-hidden />
        <span>该段没有 Markdown 正文（本地 OCR 或人工拆分不产出正文重建）</span>
      </div>
    )
  }

  const blocks = seg.blocks ?? []

  return (
    <div className="flex flex-col gap-1.5">
      <button
        type="button"
        onClick={onToggleOpen}
        aria-expanded={open}
        className="flex w-full items-center gap-1 px-1 text-left text-sm font-medium transition-colors hover:text-foreground"
      >
        {open ? (
          <ChevronDown className="h-3.5 w-3.5 flex-none" aria-hidden />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 flex-none" aria-hidden />
        )}
        <FileCode2 className="h-3.5 w-3.5 flex-none opacity-70" aria-hidden />
        <span>Markdown 正文</span>
        <span className="ml-auto flex-none text-[11px] font-normal tabular-nums text-muted-foreground">
          {seg.md.length} 字
        </span>
      </button>

      {open && (
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-1 px-1 text-[10.5px] text-muted-foreground">
            <span>
              {onEditMarkdown ? '双击定位原页 · 右键改这一行' : '双击定位到原页'}
            </span>
            {focusedBlockKey && (
              <button
                type="button"
                onClick={() => onLocateBlock(null)}
                className="ml-auto cursor-pointer underline underline-offset-2 hover:text-foreground"
              >
                取消定位
              </button>
            )}
          </div>

          {/* 列表即正文：每行就是原文的一段，改动直接在这行上做。
              不再在下方重复一份完整渲染——同一段内容出现两次，
              看的人要来回比对"刚才改的是不是这一行"。 */}
          {blocks.length > 0 ? (
            blocks.map((b, i) => {
              const key = blockKeyOf(seg, b, i)
              return (
                <BlockRow
                  key={key}
                  blockKey={key}
                  text={b.text || ''}
                  page={b.page}
                  approx={b.rect.approx}
                  active={key === focusedBlockKey}
                  editing={editingKey === key}
                  onLocate={onLocateBlock}
                  onRemove={onRemoveBlock}
                  onStartEdit={onEditBlock ? setEditingKey : undefined}
                  onCommitEdit={(text) => {
                    onEditBlock?.(key, text)
                    setEditingKey(null)
                  }}
                  onCancelEdit={() => setEditingKey(null)}
                />
              )
            })
          ) : (
            /* 没有定位块的段（本地 OCR / 旧任务）：退回整段文本编辑 */
            <WholeTextEditor
              text={seg.md}
              editing={editingAll}
              onStartEdit={onEditMarkdown ? () => setEditingAll(true) : undefined}
              onCommit={(v) => {
                onEditMarkdown?.(v)
                setEditingAll(false)
              }}
              onCancel={() => setEditingAll(false)}
            />
          )}
        </div>
      )}
    </div>
  )
}

/** 一行正文：平时是文字（双击定位），编辑态是输入框（失焦/回车保存）。 */
function BlockRow({
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
function WholeTextEditor({
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
