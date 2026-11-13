import { useState } from 'react'
import { ChevronDown, ChevronRight, FileCode2 } from 'lucide-react'

import { blockKeyOf } from '../../draft/block-keys'
import type { Segment } from '../../types'
import { cn } from '@/lib/utils'

/**
 * 分段的 Markdown 正文面板（云端识别的取字结果）。
 *
 * ## 为什么需要它
 *
 * 自动分段一直在产出 `seg.md`，但此前**没有任何 UI 展示**——它只被
 * 「识别当事人」和「推断文本」在后台消费掉。律师看不到机器读出了什么，
 * 等于整条识别链路是黑盒：分段切错了、正文缺页了，都无从发现。
 *
 * ## 「原文对照」怎么成立
 *
 * `seg.blocks` 是后端归一化的**可定位块**（`{page, text, rect}`），
 * `PageCell` 用同一份数据在页面上画定位框。两边共享 `blocks` 索引：
 * 点这里的某一条 → 通过 `onFocusBlock` 让 Flow 高亮对应页上的框。
 * 这是唯一的可靠对照方式——靠文本相似度反查会在同名标题上串行。
 *
 * ## 为什么默认折叠
 *
 * 一段正文动辄数千字，展开会把这些段落之间的页面全推到屏幕外，
 * 「边看正文边对照原页」反而做不到。默认只看页卡，需要时再展开。
 */
export function SegmentMarkdown({
  seg,
  focusedBlockKey,
  onFocusBlock,
}: {
  seg: Segment
  /** 当前高亮的块 key（与 PageCell 的 hits[].key 同一套） */
  focusedBlockKey: string | null
  onFocusBlock: (key: string | null) => void
}) {
  const [open, setOpen] = useState(false)

  // 人工拆分 / 本地 OCR / 旧任务都没有 md：明确说"没有"，而不是渲染空白
  if (!seg.md) {
    if (seg.manual) return null
    return (
      <div className="flex items-center gap-1.5 rounded-[7px] bg-secondary/40 px-2.5 py-1.5 text-[11px] text-muted-foreground">
        <FileCode2 className="h-3 w-3 flex-none opacity-60" aria-hidden />
        该段没有 Markdown 正文（本地 OCR 或人工拆分不产出正文重建）
      </div>
    )
  }

  const blocks = seg.blocks ?? []

  return (
    <div className="rounded-[7px] border border-border/70 bg-card">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-left text-[11.5px] text-muted-foreground transition-colors hover:text-foreground"
      >
        {open ? (
          <ChevronDown className="h-3 w-3 flex-none" aria-hidden />
        ) : (
          <ChevronRight className="h-3 w-3 flex-none" aria-hidden />
        )}
        <FileCode2 className="h-3 w-3 flex-none opacity-70" aria-hidden />
        <span>Markdown 正文</span>
        <span className="tabular-nums opacity-70">{seg.md.length} 字</span>
        {blocks.length > 0 && <span className="tabular-nums opacity-70">· {blocks.length} 个定位块</span>}
      </button>

      {open && (
        <div className="border-t border-border/60 px-2.5 py-2">
          {/* 定位块索引：点一条 → 原页对应框高亮（对照入口） */}
          {blocks.length > 0 && (
            <div className="mb-2 flex flex-col gap-0.5">
              <div className="mb-0.5 text-[10.5px] text-muted-foreground">
                原文对照 · 点一条去原页看框
                {focusedBlockKey && (
                  <button
                    type="button"
                    onClick={() => onFocusBlock(null)}
                    className="ml-1.5 cursor-pointer underline underline-offset-2"
                  >
                    取消高亮
                  </button>
                )}
              </div>
              {blocks.map((b, i) => {
                const key = blockKeyOf(seg, b, i)
                const active = key === focusedBlockKey
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => onFocusBlock(active ? null : key)}
                    title={`第 ${b.page} 页${b.rect.approx ? '（整页近似框）' : ''}`}
                    className={cn(
                      'flex items-start gap-1.5 rounded px-1 py-0.5 text-left text-[11px] transition-colors',
                      active ? 'bg-sky-50 text-sky-900 ring-1 ring-sky-300' : 'hover:bg-secondary/60',
                    )}
                  >
                    <span className="flex-none tabular-nums text-muted-foreground">P{b.page}</span>
                    <span className="min-w-0 flex-1 truncate">{b.text || '（空块）'}</span>
                  </button>
                )
              })}
            </div>
          )}

          {/* 正文：等宽、保留换行。这里刻意**不渲染 Markdown 语法**——
              律师要核对的是「机器读到的原文」，把 # / ** 渲染掉反而看不出解析质量 */}
          <pre className="max-h-[420px] overflow-auto whitespace-pre-wrap break-words rounded bg-secondary/40 p-2 text-[11.5px] leading-[1.7] text-foreground">
            {seg.md}
          </pre>
        </div>
      )}
    </div>
  )
}
