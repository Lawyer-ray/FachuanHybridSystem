/**
 * 合同正文双语对照（左英 / 右中）
 *
 * 录屏里最能说明「AI 真读了合同」的一屏：英文原文在左、中文对照在右，
 * 修订处红删绿增，两栏按**修订块**分栏——同一个 grid 行里左右各一个修订块，
 * 所以浏览器排版的高度变化会同时作用于两栏，不会错行。
 */

import { useState } from 'react'
import { Columns2, Eye, FileText } from 'lucide-react'

import { cn } from '@/lib/utils'

import { DEMO_NL2_CONTRACT, DEMO_REVISION_BY_ID, type DemoNl2Clause } from '../../demo-nonlit'
import { Card } from '../../ui'
import { alignClauses, type AlignedRow } from './crossborder-domain'

const RED = 'bg-status-red-bg/70 text-status-red line-through decoration-status-red/60'
const GREEN = 'bg-status-green-bg/80 text-status-green'

function Seg({ text, change }: { text: string; change?: 'mod' | 'add' }) {
  if (!text) return <span aria-hidden className="text-transparent">·</span>
  if (!change) return <>{text}</>
  return <span className={cn('rounded-[3px] px-[2px]', GREEN)}>{text}</span>
}

/** 删掉的原句（只在选中修订时出现在绿增块下方，作为 redline 的左半边） */
function Struck({ text }: { text: string }) {
  return <div className={cn('mt-1 rounded-[3px] px-[3px] text-[11px]', RED)}>{text}</div>
}

function Side({
  rows,
  side,
  focusRev,
}: {
  rows: AlignedRow[]
  side: 'en' | 'zh'
  focusRev: string | null
}) {
  return (
    <div className="flex flex-col">
      {rows.map((r) => {
        const segs = side === 'en' ? r.en : r.zh
        const hit = focusRev !== null && r.rev === focusRev
        const removed = hit && r.rev ? DEMO_REVISION_BY_ID[r.rev] : null
        return (
          <div
            key={r.key}
            data-row={r.key}
            className={cn(
              'border-t border-border-light px-3 py-2 text-[11.5px] leading-[1.75] first:border-t-0',
              hit && 'bg-status-yellow-bg/30',
            )}
          >
            {segs.map((seg, i) => (
              <Seg key={i} text={seg.text} change={seg.change} />
            ))}
            {removed ? <Struck text={side === 'en' ? removed.original : removed.originalZh} /> : null}
          </div>
        )
      })}
    </div>
  )
}

export function BilingualContractCard({
  focusRev,
  onPickRev,
}: {
  /** 高亮的修订（右侧修订清单点选后联动到这里） */
  focusRev: string | null
  onPickRev: (rev: string) => void
}) {
  const [onlyChanged, setOnlyChanged] = useState(false)
  const [showZh, setShowZh] = useState(true)

  const rows = alignClauses(DEMO_NL2_CONTRACT)
  const visible = onlyChanged ? rows.filter((r) => r.rev) : rows
  const changedCount = rows.filter((r) => r.rev).length

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-[13px] font-[620]">合同正文双语对照</h3>
        <span className="text-[11px] text-muted-foreground">
          {DEMO_NL2_CONTRACT.length} 条 · {rows.length} 句 · {changedCount} 处修订
        </span>
        <div className="ml-auto flex items-center gap-1.5">
          <button
            type="button"
            onClick={() => setOnlyChanged((v) => !v)}
            className={cn(
              'inline-flex h-[27px] items-center gap-1 rounded-[7px] border px-2 text-[11.5px] transition-colors',
              onlyChanged
                ? 'border-foreground bg-foreground font-semibold text-background'
                : 'border-border bg-card text-secondary-foreground hover:bg-secondary',
            )}
          >
            <Eye className="size-3" /> 只看修订处
          </button>
          <button
            type="button"
            onClick={() => setShowZh((v) => !v)}
            title="关闭后只留英文原文，模拟「对照关闭」"
            className={cn(
              'inline-flex h-[27px] items-center gap-1 rounded-[7px] border px-2 text-[11.5px] transition-colors',
              showZh
                ? 'border-foreground bg-foreground font-semibold text-background'
                : 'border-border bg-card text-secondary-foreground hover:bg-secondary',
            )}
          >
            <Columns2 className="size-3" /> 中文对照
          </button>
        </div>
      </div>

      <div className={cn('mt-3 overflow-hidden rounded-[10px] border border-border-light', showZh ? 'grid grid-cols-2' : 'grid grid-cols-1')}>
        <div className="border-r border-border-light bg-secondary/20">
          <div className="border-b border-border-light px-3 py-1.5 text-[10.5px] font-medium text-muted-foreground">
            ENGLISH · 出租方文本
          </div>
          <Side rows={visible} side="en" focusRev={focusRev} />
        </div>
        {showZh ? (
          <div>
            <div className="border-b border-border-light bg-secondary/20 px-3 py-1.5 text-[10.5px] font-medium text-muted-foreground">
              CHINESE · 对照译文
            </div>
            <Side rows={visible} side="zh" focusRev={focusRev} />
          </div>
        ) : null}
      </div>

      {/* 条款索引：点一下只看这一条 */}
      <div className="mt-2.5 flex flex-wrap gap-1">
        {DEMO_NL2_CONTRACT.map((c) => (
          <ClauseChip key={c.no} clause={c} onPickRev={onPickRev} />
        ))}
      </div>
    </Card>
  )
}

function ClauseChip({ clause, onPickRev }: { clause: DemoNl2Clause; onPickRev: (rev: string) => void }) {
  const hasRev = clause.revs.length > 0
  return (
    <button
      type="button"
      onClick={() => {
        if (clause.revs[0]) onPickRev(clause.revs[0])
      }}
      title={`${clause.titleEn} · ${clause.titleZh}`}
      className={cn(
        'inline-flex items-center gap-1 rounded-[6px] border px-2 text-[10.5px] leading-[1.7] transition-colors',
        hasRev
          ? 'border-status-yellow/50 bg-status-yellow-bg/60 text-status-yellow hover:bg-status-yellow-bg'
          : 'border-border-light bg-background text-muted-foreground hover:bg-secondary',
      )}
    >
      <FileText className="size-2.5" />
      ART.{clause.no}
      {hasRev ? <span className="font-semibold">· {clause.revs.length} 修订</span> : null}
    </button>
  )
}
