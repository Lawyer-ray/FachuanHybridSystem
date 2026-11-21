/**
 * 泰国法核验卡 —— 真调后端，真查 BARLC
 *
 * 与页面上另一张「外国法条核验」（演示用三道闸动画）互补：
 *   · 那张讲**原理**（法存在 → 有正文 → 条款号在范围 → 判断层）
 *   · 这张给**证据**（真查到的条文原文 + 出处 + 耗时）
 *
 * 演示时点这里最有说服力：观众看到的是从数据库实时取回来的英文条文，
 * 不是提前写在代码里的字符串。
 */

import { useState } from 'react'
import { CheckCircle2, ExternalLink, Loader2, XCircle } from 'lucide-react'

import { cn } from '@/lib/utils'

import { Card } from '../../ui'
import { TonePill as Pill } from './crossborder-ui'
import {
  DEMO_THAI_CITATIONS,
  verifyThaiLaw,
  type ForeignLawElement,
  type ForeignLawVerifyResult,
  type ThaiLawCitation,
} from './foreign-law-api'

/**
 * 判定结论 → 标签颜色与文案。
 *
 * 不用 `verdict ? '已判定' : '未判定'` 这种二元写法：`待判定` 有两种成因
 * （合议弃权 vs 合议未开启），且「原文未提及」不等于「不支持」——
 * 标签必须自己说清楚，律师才不会读反。
 */
function verdictPill(result: ForeignLawVerifyResult) {
  if (result.verdict === '支持') return <Pill tone="green">条文支持该主张</Pill>
  if (result.verdict === '矛盾') return <Pill tone="red">条文与该主张相反</Pill>
  if (result.verdict === '原文未提及') return <Pill tone="yellow">条文未涉及该主张</Pill>
  if (result.verdict === '不存在该引用') return <Pill tone="red">不存在该引用</Pill>
  if (result.adjudicated) return <Pill tone="yellow">判定器未形成多数</Pill>
  return <Pill tone="yellow">待判断层比对</Pill>
}

/** 要件判定的行内颜色 */
function elementTone(verdict: string): 'green' | 'red' | 'yellow' {
  if (verdict === '支持') return 'green'
  if (verdict === '矛盾') return 'red'
  return 'yellow'
}

function ElementRow({ element }: { element: ForeignLawElement }) {
  return (
    <li className="flex items-start gap-1.5 text-[10.5px] leading-[1.6]">
      <Pill tone={elementTone(element.verdict)}>{element.verdict}</Pill>
      <span className="min-w-0 flex-1 text-secondary-foreground">{element.statement}</span>
    </li>
  )
}

interface Row<T> {
  citation: ThaiLawCitation
  state: 'idle' | 'running' | 'done' | 'fail'
  result?: T
  error?: string
  ms?: number
}

export function ForeignLawVerifyCard() {
  const [rows, setRows] = useState<Row<ForeignLawVerifyResult>[]>(
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
          <div
            key={`${row.citation.article}-${row.citation.section}`}
            className={cn(
              'rounded-[10px] border px-3 py-2.5',
              row.state === 'done' && row.result?.ok
                ? 'border-status-green/40 bg-status-green-bg/30'
                : row.state === 'fail'
                  ? 'border-status-red/40 bg-status-red-bg/30'
                  : 'border-border-light bg-background',
            )}
          >
            {/* 抬头 */}
            <div className="flex flex-wrap items-center gap-2">
              {row.state === 'running' ? (
                <Loader2 className="size-3.5 flex-none animate-spin text-status-blue" />
              ) : row.state === 'done' && row.result?.ok ? (
                <CheckCircle2 className="size-3.5 flex-none text-status-green" />
              ) : row.state === 'fail' ? (
                <XCircle className="size-3.5 flex-none text-status-red" />
              ) : (
                <span className="size-3.5 flex-none rounded-full border border-border" />
              )}

              <span className="text-[12px] font-medium">{row.citation.article}</span>
              <Pill>{row.citation.lawName} 第 {row.citation.section} 条</Pill>

              {row.state === 'running' ? (
                <span className="text-[10.5px] text-status-blue">查询中…</span>
              ) : null}
              {row.state === 'done' && row.result?.ok ? (
                <>
                  <Pill tone="green">已取到原文</Pill>
                  {verdictPill(row.result)}
                </>
              ) : null}
              {row.state === 'fail' ? <Pill tone="red">未核验</Pill> : null}

              {row.ms ? (
                <span className="ml-auto text-[10px] tabular-nums text-muted-foreground">
                  {row.ms} ms
                </span>
              ) : null}
            </div>

            {/* 主张 */}
            <div className="mt-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">
              合同主张：{row.citation.claim}
            </div>

            {/* 逐要件判定：律师问「哪一项没依据」的答案 */}
            {row.state === 'done' && row.result?.elements?.length ? (
              <div className="mt-2 rounded-[8px] border border-border-light bg-background px-2.5 py-2">
                <div className="mb-1 flex items-center gap-1.5 text-[10px] text-muted-foreground">
                  <span className="font-medium text-foreground">逐要件判定</span>
                  {typeof row.result.agreement === 'number' ? (
                    <>
                      <span className="text-border">·</span>
                      <span className="tabular-nums">
                        一致度 {Math.round(row.result.agreement * 100)}%
                      </span>
                    </>
                  ) : null}
                </div>
                <ul className="flex flex-col gap-[3px]">
                  {row.result.elements.map((element) => (
                    <ElementRow key={element.statement} element={element} />
                  ))}
                </ul>
              </div>
            ) : null}

            {/* 必须人工复核的提示：不许只给一个绿灯就完事 */}
            {row.state === 'done' && row.result?.needs_human ? (
              <div className="mt-2 rounded-[8px] border border-status-yellow/50 bg-status-yellow-bg/50 px-2.5 py-1.5">
                <div className="text-[10px] font-medium text-status-yellow">需人工复核</div>
                <ul className="mt-[2px] flex flex-col gap-[2px]">
                  {(row.result.review_reasons ?? []).map((reason) => (
                    <li key={reason} className="text-[10.5px] leading-[1.55] text-secondary-foreground">
                      · {reason}
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}

            {/* 条文原文（真返回） */}
            {row.state === 'done' && row.result?.section_text ? (
              <div className="mt-2 rounded-[8px] border border-border-light bg-secondary/25 px-2.5 py-2">
                <div className="mb-1 flex items-center gap-1.5 text-[10px] text-muted-foreground">
                  <span>{row.result.law_title} · Section {row.result.section_number}</span>
                  <span className="text-border">·</span>
                  <span>BARLC 返回原文</span>
                </div>
                <pre className="max-h-[120px] overflow-auto whitespace-pre-wrap font-mono text-[10.5px] leading-[1.65] text-secondary-foreground">
                  {row.result.section_text}
                </pre>
              </div>
            ) : null}

            {/* 调用轨迹：让人看得出系统真的连了 BARLC，不是编的 */}
            {row.state === 'done' && row.result?.trace?.length ? (
              <div className="mt-2 rounded-[8px] border border-border-light bg-background px-2.5 py-2">
                <div className="mb-1 flex items-center gap-1.5 text-[10px] text-muted-foreground">
                  <span className="font-medium text-foreground">MCP 调用过程</span>
                  <span className="text-border">·</span>
                  <span>asean_law_verify</span>
                  <span className="text-border">·</span>
                  <span className="tabular-nums">{row.result.total_ms ?? row.ms} ms</span>
                </div>
                <ol className="flex flex-col gap-[3px]">
                  {row.result.trace.map((st, i) => (
                    <li key={st.name} className="flex items-start gap-2 text-[10.5px] leading-[1.55]">
                      <span className="w-[14px] flex-none tabular-nums text-muted-foreground">{i + 1}.</span>
                      {st.ok ? (
                        <CheckCircle2 className="mt-[2px] size-2.5 flex-none text-status-green" />
                      ) : (
                        <XCircle className="mt-[2px] size-2.5 flex-none text-status-red" />
                      )}
                      <span className="w-[92px] flex-none text-foreground">{st.name}</span>
                      <span className="min-w-0 flex-1 truncate text-muted-foreground" title={st.detail}>
                        {st.detail}
                      </span>
                      <span
                        className={cn(
                          'w-[110px] flex-none truncate text-right',
                          st.ok ? 'text-status-green' : 'text-status-red',
                        )}
                        title={st.result}
                      >
                        {st.result}
                      </span>
                    </li>
                  ))}
                </ol>
              </div>
            ) : null}

            {row.error ? (
              <div className="mt-1.5 text-[10.5px] text-status-red">{row.error}</div>
            ) : null}
          </div>
        ))}
      </div>
    </Card>
  )
}
