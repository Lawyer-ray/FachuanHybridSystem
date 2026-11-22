/**
 * 泰国法核验卡 —— 真调后端，真查 BARLC
 *
 * 与页面上另一张「外国法条核验」（演示用三道闸动画）互补：
 *   · 那张讲**原理**（法存在 → 有正文 → 条款号在范围 → 判断层）
 *   · 这张给**证据**（真查到的条文原文 + 出处 + 耗时）
 *
 * 演示时点这里最有说服力：观众看到的是从数据库实时取回来的英文条文，
 * 不是提前写在代码里的字符串。
 *
 * 本文件只留**查询状态机 + 页头**；单条引用的 8 个展示区块在 `CitationRow.tsx`。
 */

import { useState } from 'react'
import { ExternalLink, Loader2 } from 'lucide-react'

import { cn } from '@/lib/utils'

import { Card } from '../../ui'
import { CitationRow, type ForeignLawRow } from './CitationRow'
import { TonePill as Pill } from './crossborder-ui'
import { DEMO_THAI_CITATIONS, verifyThaiLaw, type ForeignLawVerifyResult } from './foreign-law-api'

export function ForeignLawVerifyCard() {
  const [rows, setRows] = useState<ForeignLawRow<ForeignLawVerifyResult>[]>(
    DEMO_THAI_CITATIONS.map((citation) => ({ citation, state: 'idle' })),
  )
  const [busy, setBusy] = useState(false)

  const doneCount = rows.filter((r) => r.state === 'done' && r.result?.ok).length
  const failCount = rows.filter((r) => r.state === 'fail').length

  /** 逐条真查 */
  const runAll = async () => {
    setBusy(true)
    setRows(DEMO_THAI_CITATIONS.map((citation) => ({ citation, state: 'idle' })))

    for (let i = 0; i < DEMO_THAI_CITATIONS.length; i++) {
      const citation = DEMO_THAI_CITATIONS[i]!
      setRows((prev) => prev.map((r, idx) => (idx === i ? { ...r, state: 'running' } : r)))
      const t0 = Date.now()
      try {
        const result = await verifyThaiLaw(citation)
        const ms = Date.now() - t0
        setRows((prev) =>
          prev.map((r, idx) =>
            idx === i
              ? { ...r, state: result.ok ? 'done' : 'fail', result, ms, error: result.ok ? undefined : result.reason }
              : r,
          ),
        )
      } catch (e) {
        const ms = Date.now() - t0
        setRows((prev) =>
          prev.map((r, idx) =>
            idx === i ? { ...r, state: 'fail', ms, error: e instanceof Error ? e.message : String(e) } : r,
          ),
        )
      }
    }
    setBusy(false)
  }

  return (
    <Card className="px-[18px] py-[15px]">
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <h3 className="text-[13px] font-[620]">外国法条核验 · 实时查询</h3>
            <Pill tone="blue">BARLC 东盟域外法律查明</Pill>
          </div>
          <p className="mt-1 max-w-[620px] text-[11.5px] leading-[1.65] text-muted-foreground">
            下面每一条都是现查现取：调「一带一路」沿线国家或地区法律查明服务，
            取回该条文的英文原文。查到什么就显示什么，查不到就报查不到。
          </p>
        </div>
        <div className="flex flex-none flex-col items-end gap-1.5">
          <button
            type="button"
            disabled={busy}
            onClick={() => void runAll()}
            className={cn(
              'inline-flex h-[31px] items-center gap-1.5 rounded-[8px] border border-foreground bg-foreground px-[13px] text-[12.5px] font-semibold text-background transition-opacity hover:opacity-85',
              busy && 'opacity-60',
            )}
          >
            {busy ? <Loader2 className="size-3.5 animate-spin" /> : <ExternalLink className="size-3.5" />}
            {busy ? '正在查询…' : doneCount > 0 ? '重新核验' : '核验这 3 条'}
          </button>
          <span className="text-[10px] text-muted-foreground">
            {doneCount > 0 || failCount > 0
              ? `通过 ${doneCount} / 失败 ${failCount} · 每条约 6-8 秒`
              : '3 条引用 · 每条约 6-8 秒'}
          </span>
        </div>
      </div>

      <div className="mt-3 flex flex-col gap-2">
        {rows.map((row) => (
          <CitationRow key={`${row.citation.article}-${row.citation.section}`} row={row} />
        ))}
      </div>
    </Card>
  )
}
