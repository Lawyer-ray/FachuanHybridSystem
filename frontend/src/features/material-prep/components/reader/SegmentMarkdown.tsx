import { useState } from 'react'
import { Check, ChevronDown, ChevronRight, FileCode2, PencilLine, Trash2 } from 'lucide-react'

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
  /** 手改正文（识别错字/表格拍平时律师自己修） */
  onEditMarkdown?: (md: string) => void
  /** 删掉一个画错的定位框（只删坐标，不动正文） */
  onRemoveBlock?: (key: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draftText, setDraftText] = useState('')

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

      {/* 识别不可能全对（表格拍平、标题层级错、页眉混进正文）。
          改过的内容进草稿，可撤销、随包保存——不是本地方便改一下就没了。 */}
      {onEditMarkdown && open && !editing && (
        <button
          type="button"
          onClick={() => {
            setDraftText(seg.md ?? '')
            setEditing(true)
          }}
          className="ml-auto flex items-center gap-1 self-end rounded px-1.5 py-0.5 text-[11px] text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
        >
          <PencilLine className="h-3 w-3" aria-hidden />
          改正文
        </button>
      )}

      {open && (
        <div className="flex flex-col gap-2">
          {blocks.length > 0 && (
            <div className="flex flex-col gap-0.5">
              <div className="flex items-center gap-1 px-1 text-[10.5px] text-muted-foreground">
                <span>双击定位到原页</span>
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
              {blocks.map((b, i) => {
                const key = blockKeyOf(seg, b, i)
                const active = key === focusedBlockKey
                return (
                  <div key={key} className="group/row flex items-start gap-0.5">
                    <button
                      type="button"
                      // 双击才定位：单击是阅读时的选中动作，不该触发跳转
                      onDoubleClick={() => onLocateBlock(active ? null : key)}
                      title={`第 ${b.page} 页${b.rect.approx ? '（整页近似框）' : ''} · 双击定位`}
                      className={cn(
                        'flex min-w-0 flex-1 items-start gap-1.5 rounded px-1.5 py-1 text-left text-[11px] leading-relaxed transition-colors',
                        active ? 'bg-sky-50 text-sky-900 ring-1 ring-sky-300' : 'hover:bg-secondary/60',
                      )}
                    >
                      <span className="flex-none tabular-nums text-muted-foreground">P{b.page}</span>
                      <span className="line-clamp-2 min-w-0 flex-1">{b.text || '（空块）'}</span>
                    </button>
                    {/* 框画歪了就删掉——只删这个坐标，不影响正文 */}
                    {onRemoveBlock && (
                      <button
                        type="button"
                        onClick={() => onRemoveBlock(key)}
                        title="这个定位框画错了：删掉它（不影响正文）"
                        aria-label="删除这个定位框"
                        className="mt-1 grid h-4 w-4 flex-none place-items-center rounded text-zinc-300 opacity-0 transition-opacity hover:text-destructive focus-visible:opacity-100 group-hover/row:opacity-100 [@media(hover:none)]:opacity-100"
                      >
                        <Trash2 className="h-3 w-3" />
                      </button>
                    )}
                  </div>
                )
              })}
            </div>
          )}

          {/* 正文：等宽、保留换行。刻意**不渲染 Markdown 语法**——
              律师要核对的是「机器读到的原文」，把 # / ** 渲染掉反而看不出解析质量 */}
          {editing ? (
            <div className="flex flex-col gap-1">
              <textarea
                autoFocus
                value={draftText}
                onChange={(e) => setDraftText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Escape') setEditing(false)
                }}
                spellCheck={false}
                className="max-h-[46vh] min-h-[160px] w-full resize-y overflow-auto rounded-lg border border-sky-300 bg-white p-2 font-mono text-[11px] leading-[1.7] outline-none focus:ring-1 focus:ring-sky-400"
              />
              <div className="flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={() => {
                    onEditMarkdown?.(draftText)
                    setEditing(false)
                  }}
                  className="flex items-center gap-1 rounded-md bg-zinc-900 px-2 py-1 text-[11px] font-medium text-white hover:bg-zinc-800"
                >
                  <Check className="h-3 w-3" aria-hidden />
                  保存
                </button>
                <button
                  type="button"
                  onClick={() => setEditing(false)}
                  className="rounded-md border border-border px-2 py-1 text-[11px] hover:bg-secondary"
                >
                  取消
                </button>
                <span className="ml-auto text-[10.5px] text-muted-foreground">
                  改过的正文进草稿，可撤销
                </span>
              </div>
            </div>
          ) : (
            <pre className="max-h-[46vh] overflow-auto whitespace-pre-wrap break-words rounded-lg border border-zinc-200 bg-secondary/40 p-2 text-[11px] leading-[1.7] text-foreground">
              {seg.md}
            </pre>
          )}
        </div>
      )}
    </div>
  )
}
