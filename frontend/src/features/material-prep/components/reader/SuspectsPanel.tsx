import { useState } from 'react'
import { AlertTriangle, ChevronDown, ChevronRight } from 'lucide-react'

import { findSuspects, type MdSuspect } from '../../draft/md-suspects'
import { locateKeyOf } from '../../draft/block-keys'
import type { Segment } from '../../types'
import { cn } from '@/lib/utils'

/**
 * 正文「可疑点」清单。
 *
 * ## 为什么是清单，不是行内小圆点
 *
 * `findSuspects` 给的是 **markdown 行号**，而面板渲染的是 `seg.blocks`（后端定位块）。
 * 两者没有对应关系：`seg.md` 是后端把标题 + 各页块用空行拼起来的，一个表格块在 md 里
 * 会展开成几十行。按行号把点画到 block 上必然**指错行**——标记指错比没有标记更糟，
 * 律师会连带不信任其它正确的标记。
 *
 * 也不能退化成「按块聚合」：92 行流水会全标在同一个 block 上，一个点代表 50 处问题，
 * 等于没有标记。
 *
 * ## 所以清单里每条都带「原文 + 跳转」
 *
 * 律师真正要的是两件事：**是哪个数**、**在原件哪一页**。所以每条显示命中的原文片段
 * （`match`），并给一个「查看原页」——用文本匹配找出该片段所在的 block，再交给
 * `onLocateBlock` 定位。匹配不到就**不显示按钮**：宁可少一个入口，也不给假跳转。
 *
 * ## 排序与折叠
 *
 * high 在前（最该看的永远在最上面），同级按出现顺序。超过 {@link COLLAPSE_AT} 条默认
 * 折叠：一份流水段能出几十条，默认全展开会把正文挤没。
 */

/** 超过这个条数默认折叠 */
const COLLAPSE_AT = 5

/** 排序：high 优先，同级按行序（即原文顺序） */
function sortSuspects(list: MdSuspect[]): MdSuspect[] {
  return [...list].sort((a, b) => {
    if (a.severity !== b.severity) return a.severity === 'high' ? -1 : 1
    return a.lineIndex - b.lineIndex
  })
}

/** 段头汇总：有高危才出现；数字分别给「总数」与「高危数」 */
export function SuspectSummary({ suspects }: { suspects: MdSuspect[] }) {
  if (suspects.length === 0) return null
  const high = suspects.filter((s) => s.severity === 'high').length
  return (
    <div className="flex items-start gap-1 rounded border border-amber-200 bg-amber-50/70 px-1.5 py-1 text-[10.5px] leading-relaxed text-amber-800">
      <AlertTriangle className="mt-px h-3 w-3 flex-none text-amber-600" aria-hidden />
      <span>
        本段有 {suspects.length} 处可疑{high > 0 ? `（${high} 处高危）` : ''}
      </span>
    </div>
  )
}

/** 一条可疑点：等级点 + 提示 + 命中原文 + 「查看原页」 */
function SuspectItem({ seg, suspect, onLocate }: { seg: Segment; suspect: MdSuspect; onLocate: (key: string | null) => void }) {
  const high = suspect.severity === 'high'
  const key = locateKeyOf(seg, suspect)
  return (
    <div className="flex items-start gap-1.5 px-1.5 py-1 text-[10.5px] leading-relaxed">
      <span
        className={cn('mt-1 h-1.5 w-1.5 flex-none rounded-full', high ? 'bg-amber-600' : 'bg-zinc-400')}
        aria-hidden
      />
      <div className="flex min-w-0 flex-1 flex-wrap items-baseline gap-x-1.5">
        <span className={cn('flex-none', high ? 'text-amber-800' : 'text-muted-foreground')}>{suspect.hint}</span>
        {/* 命中原文：律师一眼就知道是哪个数、哪个日期 */}
        {suspect.match && (
          <code className={cn('rounded bg-secondary px-1 font-mono', high ? 'text-amber-900' : 'text-foreground')}>
            {suspect.match}
          </code>
        )}
        {/* 匹配不到对应块就不给按钮——不做假跳转 */}
        {key && (
          <button
            type="button"
            onClick={() => onLocate(key)}
            className="flex-none cursor-pointer underline underline-offset-2 hover:text-foreground"
          >
            查看原页
          </button>
        )}
      </div>
    </div>
  )
}

/**
 * 可疑点清单本体（段头汇总 + 可折叠列表）。
 *
 * 放在正文列表之后：律师是先读正文，读到觉得不对的地方再回头查清单。
 */
export function SuspectsPanel({ seg, onLocate }: { seg: Segment; onLocate: (key: string | null) => void }) {
  const suspects = sortSuspects(findSuspects(seg.md ?? ''))
  // 条数多时默认折叠；用户手动切过之后由 expanded 作主
  const [expanded, setExpanded] = useState(false)
  if (suspects.length === 0) return null

  const collapsible = suspects.length > COLLAPSE_AT
  const showList = !collapsible || expanded

  return (
    <div className="flex flex-col gap-1 rounded-lg border border-amber-200/70 bg-amber-50/30 p-1">
      {collapsible ? (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="flex w-full items-center gap-1 rounded px-1.5 py-1 text-left text-[10.5px] font-medium text-amber-800 hover:bg-amber-100/60"
        >
          {expanded ? (
            <ChevronDown className="h-3 w-3 flex-none" aria-hidden />
          ) : (
            <ChevronRight className="h-3 w-3 flex-none" aria-hidden />
          )}
          <AlertTriangle className="h-3 w-3 flex-none text-amber-600" aria-hidden />
          <span>{suspects.length} 处可疑</span>
          <span className="ml-auto font-normal text-amber-700">{expanded ? '收起' : '展开'}</span>
        </button>
      ) : (
        <SuspectSummary suspects={suspects} />
      )}

      {showList && (
        <div className="flex flex-col divide-y divide-amber-200/50">
          {suspects.map((s, i) => (
            <SuspectItem key={`${s.kind}:${s.lineIndex}:${i}`} seg={seg} suspect={s} onLocate={onLocate} />
          ))}
        </div>
      )}
    </div>
  )
}
