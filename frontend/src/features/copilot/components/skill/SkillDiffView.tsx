/**
 * 两版正文的行级 diff（纯展示，不取数、不发请求）。
 *
 * 为什么用 `<ins>` / `<del>` 而不是自己画两个色块：语义标签本身就把「这行是新增」说给
 * 屏幕阅读器与复制粘贴听，不需要引入富文本 diff 库（那类库会连样式带解析器一起进来，
 * 而这里的数据已经是服务端拆好的 `{op, lines}`）。
 *
 * 未改动的上下文默认折叠（超过 6 行）：审批人要判的是「这次改了什么」，把一份 32KB
 * 的正文整篇铺开会让真正的改动淹在里面。折叠不丢信息——点一下就看得到全部，且折叠的
 * 是**未改动段**，改动行一行都不折。
 *
 * 两版相同（首次发布：线上还没有版本，两侧都取工作区）时明说「与线上版本一致」：
 * 一句空白会让人以为 diff 加载失败。
 */

import { useState } from 'react'

import { StatusBadge } from '@/components/shared/StatusBadge'
import type { AgentSkillDiff, AgentSkillDiffHunk } from '../../skill-types'

/** 未改动上下文超过这么多行就折叠成一行提示 */
const CONTEXT_FOLD_LIMIT = 6

/** 空行也要占一行高度，否则折叠后的行数对不上、`\n\n` 段落会视觉消失 */
const BLANK = '\u00a0'

/** 改动行数（不含未改动行）：徽标用它，0 就是「两版一致」 */
function changedLineCount(hunks: AgentSkillDiffHunk[]): number {
  return hunks.reduce((total, hunk) => (hunk.op === 'equal' ? total : total + hunk.lines.length), 0)
}

/** 一行未改动的上下文（中性灰，不做底色，改动行才需要颜色） */
function ContextLine({ line }: { line: string }) {
  return (
    <div className="whitespace-pre-wrap break-words px-2.5 font-mono text-[11.5px] leading-relaxed text-muted-foreground">
      {line === '' ? BLANK : line}
    </div>
  )
}

/** 一行改动：`ins` / `del` 用对应语义标签（同一份内容两种标签，分支写开更好读） */
function ChangedLine({ line, op }: { line: string; op: 'ins' | 'del' }) {
  const inserted = op === 'ins'
  const className = `block whitespace-pre-wrap break-words px-2.5 font-mono text-[11.5px] leading-relaxed text-foreground ${
    inserted ? 'bg-status-green-bg/60' : 'bg-status-red-bg/60'
  }`
  const content = (
    <>
      <span className={inserted ? 'mr-1 text-status-green' : 'mr-1 text-status-red'}>{inserted ? '+' : '−'}</span>
      {line === '' ? BLANK : line}
    </>
  )
  return inserted ? <ins className={className}>{content}</ins> : <del className={className}>{content}</del>
}

/** 一个 hunk：`equal` 走上下文样式（可折叠），`ins` / `del` 逐行走 `ChangedLine` */
function DiffHunk({ hunk, folded, onExpand }: { hunk: AgentSkillDiffHunk; folded: boolean; onExpand: () => void }) {
  if (hunk.op === 'equal') {
    if (folded) {
      return (
        <button
          type="button"
          onClick={onExpand}
          className="block w-full px-2.5 py-1 text-left text-[10.5px] text-muted-foreground transition-colors hover:bg-secondary"
        >
          … 还有 {hunk.lines.length} 行未改动，点开查看
        </button>
      )
    }
    return (
      <>
        {hunk.lines.map((line, index) => (
          <ContextLine key={`equal-${index}`} line={line} />
        ))}
      </>
    )
  }

  // 收窄写进局部常量：`hunk.op` 是属性访问，narrowing 不会流进 map 的回调
  const op: 'ins' | 'del' = hunk.op === 'ins' ? 'ins' : 'del'
  return (
    <>
      {hunk.lines.map((line, index) => (
        <ChangedLine key={`${op}-${index}`} line={line} op={op} />
      ))}
    </>
  )
}

export function SkillDiffView({ diff }: { diff: AgentSkillDiff }) {
  /** 已展开的 hunk 下标（按块记，不按行，展开后整块原样铺开） */
  const [expanded, setExpanded] = useState<Record<number, boolean>>({})
  const changes = changedLineCount(diff.hunks)

  return (
    <section aria-label="改动对比" className="overflow-hidden rounded-[9px] border border-border bg-card">
      <header className="flex flex-wrap items-center gap-2 border-b border-border px-2.5 py-1.5">
        <span className="text-[11px] text-muted-foreground">
          线上第 {diff.v1} 版 → 工作区第 {diff.v2} 版
        </span>
        <span className="ml-auto">
          <StatusBadge tone={changes > 0 ? 'yellow' : 'neutral'} size="xs">
            {changes > 0 ? `${changes} 行改动` : '无改动'}
          </StatusBadge>
        </span>
      </header>

      {changes === 0 ? (
        <p className="px-2.5 py-3 text-[11.5px] leading-relaxed text-muted-foreground">
          与线上版本一致：这次提审没有改动正文。
        </p>
      ) : (
        // max-h + overflow：长正文在抽屉里仍然只占一屏，审批动作不会被挤到看不见的地方
        <div className="max-h-[46vh] overflow-y-auto py-1">
          {diff.hunks.map((hunk, index) => (
            <DiffHunk
              key={`${hunk.op}-${index}`}
              hunk={hunk}
              folded={hunk.op === 'equal' && hunk.lines.length > CONTEXT_FOLD_LIMIT && expanded[index] !== true}
              onExpand={() => setExpanded((prev) => ({ ...prev, [index]: true }))}
            />
          ))}
        </div>
      )}
    </section>
  )
}
