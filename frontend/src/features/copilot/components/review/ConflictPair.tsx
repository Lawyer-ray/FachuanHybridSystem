/**
 * 一个分歧点：同一条 rubric 上各栏判断相反，两侧**原句并排**。
 *
 * 为什么并排原句而不是只写「两栏意见不同」：律师要判断的是哪一句站得住，
 * 判断依据只能是 judge 各自引的原文；把原句并排放，才看得到分歧究竟在
 * 「合同里有没有这条」还是「同一条读出了两种效果」。
 *
 * 判不了的栏不进这里（它不是一方立场，见 domain/fusion 的 `conflictPairsOf`），
 * 所以每侧都必然有明确的成立/不成立。
 */

import type { ConflictPairView } from '../../domain/fusion'

export function ConflictPair({ pair }: { pair: ConflictPairView }) {
  return (
    <li data-testid={`conflict-${pair.rubricId}`} className="min-w-0">
      <div className="font-mono text-[10px] text-muted-foreground">{pair.rubricId}</div>
      <div className="mt-0.5 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
        {pair.sides.map((side) => (
          <div key={side.lane} className="min-w-0 rounded-[6px] border border-border bg-background/60 p-1.5">
            <div className={`text-[10px] ${side.met ? 'text-emerald-600 dark:text-emerald-400' : 'text-destructive'}`}>
              {side.label} · {side.met ? '认为成立' : '认为不成立'}
            </div>
            {side.evidenceQuote ? (
              <blockquote className="mt-0.5 text-[11px] leading-relaxed">“{side.evidenceQuote}”</blockquote>
            ) : (
              // judge 没给原文时如实说，不拿解释冒充原句
              <p className="mt-0.5 text-[11px] text-muted-foreground">（judge 未附原文）</p>
            )}
          </div>
        ))}
      </div>
    </li>
  )
}
