import { useEffect, useState } from 'react'
import { ChevronDown, ChevronRight, FileCode2 } from 'lucide-react'

import { blockKeyOf } from '../../draft/block-keys'
import type { Segment } from '../../types'
import { BlockRow, WholeTextEditor } from './SegmentRow'
import { SuspectsPanel } from './SuspectsPanel'

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
 *
 * ## 可疑点标记
 *
 * 识别不可能全对（OCR 认错数字/日期、表格拍平、空块……），但律师没法拿一段几千字
 * 的正文逐字核对原页——于是 `findSuspects` 给出可疑点，这里在正文下方挂一个可折叠
 * 清单（每条带命中原文 + 「查看原页」）。
 *
 * **为什么不在行内画小圆点**：`findSuspects` 的行号是 markdown 行号，而面板渲染的是
 * `blocks`，两者无对应关系（一个表格块在 md 里展开成几十行），按行号画必然指错行。
 * 标注指错比不标注更糟——律师会连带不信其它正确的标注。详细权衡见 `SuspectsPanel.tsx`。
 */
export function SegmentMarkdown({
  seg,
  open,
  onToggleOpen,
  focusedBlockKey,
  onLocateBlock,
  editRequestKey,
  onEditRequestHandled,
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
  /**
   * 「请对这块进入修改态」的一次性请求（来自页面框双击）。
   * 消费后要调 `onEditRequestHandled` 清空，否则后续同块高亮会反复弹输入框。
   */
  editRequestKey?: string | null
  onEditRequestHandled?: () => void
  /** 手改正文（识别错字/表格拍平时律师自己修）——没有定位块时的整段编辑 */
  onEditMarkdown?: (md: string) => void
  /** 改某一行（定位块）的文字；同步进 Markdown 正文 */
  onEditBlock?: (key: string, text: string) => void
  /** 删掉一个画错的定位框（只删坐标，不动正文） */
  onRemoveBlock?: (key: string) => void
}) {
  // 正在编辑的那一行的 key；null = 全部只读
  const [editingKey, setEditingKey] = useState<string | null>(null)

  /**
   * 页面框双击 → 自动进入这一行的修改态。
   *
   * 用 effect 而不是在渲染里直接 setEditingKey：渲染期改 state 会触发
   * React 的重渲染警告，而且这个信号是「事件驱动的副作用」，本就属于 effect。
   * 消费完立即回调清空，保证一次性语义（否则同一块再高亮会又弹一次输入框）。
   */
  useEffect(() => {
    if (!editRequestKey) return
    if (!onEditBlock) {
      // 没有逐块编辑能力（无定位块的段）：退回整段编辑
      if (onEditMarkdown) setEditingAll(true)
    } else {
      setEditingKey(editRequestKey)
    }
    onEditRequestHandled?.()
  }, [editRequestKey, onEditBlock, onEditMarkdown, onEditRequestHandled])
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

          {/* 可疑点清单：放在正文之后。先读正文，读到觉得不对的地方再回头查清单。 */}
          <SuspectsPanel seg={seg} onLocate={onLocateBlock} />
        </div>
      )}
    </div>
  )
}
