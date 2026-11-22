/**
 * 泰国法核验 · 单条引用的全部区块（抬头 / 主张 / 时效告警 / 逐要件 / 需人工复核 /
 * 条文原文 / 指定款 / MCP 调用轨迹 / 错误）。
 *
 * 拆自 `ForeignLawVerifyCard.tsx`（原单函数 260 行里，这 8 个互不依赖的展示区块
 * 占了大半）。本组件**没有内部状态**，只按传入的查询结果渲染——状态机留在卡片里。
 */

import { CheckCircle2, ExternalLink, Loader2, TriangleAlert, XCircle } from 'lucide-react'

import { cn } from '@/lib/utils'

import { TonePill as Pill } from './crossborder-ui'
import type { ForeignLawElement, ForeignLawVerifyResult, ThaiLawCitation } from './foreign-law-api'

/** 一条引用的查询状态与结果 */
export interface ForeignLawRow<T> {
  citation: ThaiLawCitation
  state: 'idle' | 'running' | 'done' | 'fail'
  result?: T
  error?: string
  ms?: number
}

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

function ElementList({ elements }: { elements: ForeignLawElement[] }) {
  return (
    <ul className="flex flex-col gap-[3px]">
      {elements.map((element) => (
        <li key={element.statement} className="flex items-start gap-1.5 text-[10.5px] leading-[1.6]">
          <Pill tone={elementTone(element.verdict)}>{element.verdict}</Pill>
          <span className="min-w-0 flex-1 text-secondary-foreground">{element.statement}</span>
        </li>
      ))}
    </ul>
  )
}

/** 调用轨迹：让人看得出系统真的连了 BARLC，不是编的 */
function TraceList({ trace }: { trace: NonNullable<ForeignLawVerifyResult['trace']> }) {
  return (
    <ol className="flex flex-col gap-[3px]">
      {trace.map((st, i) => (
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
            className={cn('w-[110px] flex-none truncate text-right', st.ok ? 'text-status-green' : 'text-status-red')}
            title={st.result}
          >
            {st.result}
          </span>
        </li>
      ))}
    </ol>
  )
}

export function CitationRow({ row }: { row: ForeignLawRow<ForeignLawVerifyResult> }) {
  return (
    <div
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
        <Pill>
          {row.citation.lawName} 第 {row.citation.section} 条
        </Pill>

        {row.state === 'running' ? <span className="text-[10.5px] text-status-blue">查询中…</span> : null}
        {row.state === 'done' && row.result?.ok ? (
          <>
            <Pill tone="green">已取到原文</Pill>
            {verdictPill(row.result)}
          </>
        ) : null}
        {row.state === 'fail' ? <Pill tone="red">未核验</Pill> : null}

        {row.ms ? <span className="ml-auto text-[10px] tabular-nums text-muted-foreground">{row.ms} ms</span> : null}
      </div>

      {/* 主张 */}
      <div className="mt-1.5 text-[10.5px] leading-[1.6] text-muted-foreground">合同主张：{row.citation.claim}</div>

      {/* 时效告警：这类问题必须显性展示，不能藏在一个绿 pill 后面 */}
      {row.state === 'done' && row.result?.version_warnings?.length ? (
        <div className="mt-2 rounded-[8px] border border-status-yellow/50 bg-status-yellow-bg/50 px-2.5 py-1.5">
          <div className="flex items-center gap-1.5 text-[10px] font-medium text-status-yellow">
            <TriangleAlert className="size-3" />
            生效版本提示
          </div>
          <ul className="mt-[2px] flex flex-col gap-[2px]">
            {row.result.version_warnings.map((warning) => (
              <li key={warning} className="text-[10.5px] leading-[1.55] text-secondary-foreground">
                · {warning}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {/* 逐要件判定：律师问「哪一项没依据」的答案 */}
      {row.state === 'done' && row.result?.elements?.length ? (
        <div className="mt-2 rounded-[8px] border border-border-light bg-background px-2.5 py-2">
          <div className="mb-1 flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <span className="font-medium text-foreground">逐要件判定</span>
            {typeof row.result.agreement === 'number' ? (
              <>
                <span className="text-border">·</span>
                <span className="tabular-nums">一致度 {Math.round(row.result.agreement * 100)}%</span>
              </>
            ) : null}
          </div>
          <ElementList elements={row.result.elements} />
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
            <span>
              {row.result.law_title} · Section {row.result.section_number}
            </span>
            <span className="text-border">·</span>
            <span>BARLC 返回原文</span>
            {row.result.source_url ? (
              <a
                href={row.result.source_url}
                target="_blank"
                rel="noreferrer"
                className="ml-auto inline-flex items-center gap-0.5 text-status-blue hover:underline"
              >
                原站打开
                <ExternalLink className="size-2.5" />
              </a>
            ) : null}
          </div>
          <pre className="max-h-[120px] overflow-auto whitespace-pre-wrap font-mono text-[10.5px] leading-[1.65] text-secondary-foreground">
            {row.result.section_text}
          </pre>
        </div>
      ) : null}

      {/* 指定到款时把该款正文单独标出来（判定仍基于整条，见后端说明） */}
      {row.state === 'done' && row.result?.matched_paragraph ? (
        <div className="mt-2 rounded-[8px] border border-status-blue/40 bg-status-blue-bg/30 px-2.5 py-2">
          <div className="mb-1 text-[10px] text-muted-foreground">引用指定到该款（判定仍基于整条原文）</div>
          <pre className="whitespace-pre-wrap font-mono text-[10.5px] leading-[1.65] text-secondary-foreground">
            {row.result.matched_paragraph}
          </pre>
        </div>
      ) : null}

      {/* 调用轨迹 */}
      {row.state === 'done' && row.result?.trace?.length ? (
        <div className="mt-2 rounded-[8px] border border-border-light bg-background px-2.5 py-2">
          <div className="mb-1 flex items-center gap-1.5 text-[10px] text-muted-foreground">
            <span className="font-medium text-foreground">MCP 调用过程</span>
            <span className="text-border">·</span>
            <span>asean_law_verify</span>
            <span className="text-border">·</span>
            <span className="tabular-nums">{row.result.total_ms ?? row.ms} ms</span>
          </div>
          <TraceList trace={row.result.trace} />
        </div>
      ) : null}

      {row.error ? <div className="mt-1.5 text-[10.5px] text-status-red">{row.error}</div> : null}
    </div>
  )
}
