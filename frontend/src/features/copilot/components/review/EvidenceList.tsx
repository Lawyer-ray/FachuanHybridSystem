/**
 * 一栏的逐条判定（点分数展开）：rubric 条目 → 判定 → 原文片段。
 *
 * 「点开分数看证据」的数据源全在 `CriteriaVerdict` 里：`evidence_quote` 是 judge
 * 引用的原文，`explanation` 是它的理由。判不了（`met === null`）的条目**必须显示
 * 原因**——只标一个「判不了」等于让律师以为模型看过但没表态，而实际可能是超时、
 * 解析失败或协议偏离，这三种的可信度完全不同。
 */

import type { VerdictView } from '../../domain'

const VERDICT_TONE: Record<'yes' | 'no' | 'unscored', string> = {
  yes: 'text-emerald-600 dark:text-emerald-400',
  no: 'text-destructive',
  unscored: 'text-amber-600 dark:text-amber-500',
}

function verdictText(verdict: VerdictView): { text: string; tone: keyof typeof VERDICT_TONE } {
  if (verdict.met === true) return { text: '通过', tone: 'yes' }
  if (verdict.met === false) return { text: '不通过', tone: 'no' }
  return {
    text: verdict.unscoredReason ? `判不了 · ${verdict.unscoredReason}` : '判不了',
    tone: 'unscored',
  }
}

export function EvidenceList({ verdicts, laneLabel }: { verdicts: VerdictView[]; laneLabel: string }) {
  if (verdicts.length === 0) {
    return <p className="mt-1 pl-2 text-[11px] text-muted-foreground">该栏没有逐条判定</p>
  }
  return (
    <ul className="mt-1 space-y-1 border-l-2 border-border pl-2" aria-label={`${laneLabel} 的逐条判定`}>
      {verdicts.map((verdict) => {
        const { text, tone } = verdictText(verdict)
        return (
          <li key={verdict.rubricId} data-testid="evidence-item">
            <div className="flex flex-wrap items-baseline gap-x-1.5 text-[11px]">
              <span className="font-mono text-[10px] text-muted-foreground">{verdict.rubricId}</span>
              <span className={VERDICT_TONE[tone]}>{text}</span>
              {verdict.judgeModel && <span className="text-[10px] text-muted-foreground">{verdict.judgeModel}</span>}
              {verdict.attempts > 1 && <span className="text-[10px] text-muted-foreground">重试 {verdict.attempts} 次</span>}
            </div>
            {verdict.explanation && (
              <p className="mt-0.5 text-[11px] leading-relaxed text-muted-foreground">{verdict.explanation}</p>
            )}
            {verdict.evidenceQuote && (
              <blockquote
                data-testid="evidence-quote"
                className="mt-0.5 border-l border-border pl-1.5 text-[11px] leading-relaxed text-foreground/80"
              >
                “{verdict.evidenceQuote}”
              </blockquote>
            )}
          </li>
        )
      })}
    </ul>
  )
}
