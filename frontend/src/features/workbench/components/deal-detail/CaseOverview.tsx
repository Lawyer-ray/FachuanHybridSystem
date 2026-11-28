import { useMemo, useState } from 'react'

import type { DealCase } from '../../types'
import { STAGE_ORDER, caseBranches, orderChain } from './detail-domain'
import { Card, SegBtn, StateDot } from './ui'

/**
 * 多程序线案件总览（`multi` 形态的顶部块）。
 *
 * 什么时候走到这里：一个委托下挂着两条及以上互不相干的程序线——两个被告各自一审+执行
 * （261 号）、两个二审只有一个进了执行（271 号）、系列案里 14 个不同案由的平行案件。这些情况画横向进度条会说假话：同阶段多案只能压成 `×N`，而 `×N` 读起来像
 * 「两条都走到这一步了，还差 N-1 个」。
 *
 * 换成一案一行的清单：
 * - 每行左边是该案所在**程序线**的小链点（关系已知时才有多点，单案线就一个点）。
 *   这是进度条唯一有正经价值的那个问题——「这一步后面还有没有程序」——的逐案版本；
 * - 行可点，滚到下面那张案件卡并高亮（复用页面级 `jump`）；
 * - 默认按案由分组（系列案一眼看出「这批买卖合同、这批劳动争议」）；案由只有一个时
 *   自动按程序分组（261 就是「两个一审已结 / 两个执行在办」）。
 *
 * 故意**不**用后端的 `group_key` 分组：那个字段只有归档/复制路径会拷，常规建案不写，
 * 现在基本是空的，拿它分组只会把所有案件并进一个「未分组」。
 */
export function CaseOverview({ cases, onJump }: { cases: DealCase[]; onJump: (caseId: number) => void }) {
  const branches = useMemo(() => caseBranches(cases), [cases])
  /** 每案对应的整条程序线（同线案件用于画小链点） */
  const lineOf = useMemo(() => {
    const m = new Map<number, DealCase[]>()
    for (const b of branches) for (const c of b) m.set(c.id, b)
    return m
  }, [branches])

  /**
   * 分组维度。默认值由数据决定而不是写死：案由多样（系列案）先按案由分，
   * 案由只有一种（261）按案由分就是一整块，等于没分——那种情况按程序分才有信息量。
   */
  const causes = useMemo(() => new Set(cases.map((c) => c.cause || '未填案由')), [cases])
  const [modeOverride, setModeOverride] = useState<'cause' | 'stage' | null>(null)
  const mode = modeOverride ?? (causes.size > 1 ? 'cause' : 'stage')

  const groups = useMemo(() => {
    const key = (c: DealCase) => (mode === 'cause' ? c.cause || '未填案由' : c.proc)
    const m = new Map<string, DealCase[]>()
    for (const c of orderChain(cases)) {
      const list = m.get(key(c))
      if (list) list.push(c)
      else m.set(key(c), [c])
    }
    const rank = (s: string) => {
      const i = STAGE_ORDER.indexOf(s)
      return i === -1 ? STAGE_ORDER.length : i
    }
    // 按程序分组时用程序序（一审 → 二审 → 执行），不是拼音序；
    // 按案由分组时案件多的在前（系列案里 22 人那类打包案会自然浮到顶上），同数按名称排
    return [...m.entries()].sort((a, b) =>
      mode === 'stage' ? rank(a[0]) - rank(b[0]) || a[0].localeCompare(b[0]) : b[1].length - a[1].length || a[0].localeCompare(b[0]),
    )
  }, [cases, mode])

  const done = cases.filter((c) => c.done).length

  return (
    <Card className="mb-[18px] px-5 py-[13px] max-[680px]:px-3.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
        {/* 这里不写「N 条程序线」：库里大部分案件没有 previous_case，真实分线数不可知，
            「N 条」会把「不知道」说成「确定是 N 条」。只报数得出来的东西。 */}
        <span className="text-[13.5px] font-[620] tabular-nums">{cases.length} 个案件</span>
        <span className="text-xs text-muted-foreground tabular-nums">
          {cases.length - done} 在办 · {done} 已结
        </span>
        <span className="ml-auto flex flex-none rounded-[7px] border border-border-light p-[2px]">
          <SegBtn active={mode === 'cause'} onClick={() => setModeOverride('cause')}>
            按案由
          </SegBtn>
          <SegBtn active={mode === 'stage'} onClick={() => setModeOverride('stage')}>
            按程序
          </SegBtn>
        </span>
      </div>

      <div className="mt-1.5 flex flex-col">
        {groups.map(([title, rows]) => (
          <div key={title}>
            {/* 只有一组时组标题等于整块的标签，重复一遍反而像两个层级 */}
            {groups.length > 1 && (
              <div className="mt-2 mb-px flex items-baseline gap-2">
                <h4 className="text-[11px] font-[650] tracking-[0.06em] text-muted-foreground/80">{title}</h4>
                <span className="text-[11px] text-muted-foreground/50 tabular-nums">{rows.length}</span>
              </div>
            )}
            {rows.map((c) => (
              <CaseRow key={c.id} c={c} line={lineOf.get(c.id) ?? [c]} onJump={onJump} />
            ))}
          </div>
        ))}
      </div>
    </Card>
  )
}

/** 一行 = 一个案子：程序线小链点 + 案名 + 机构（系列案里案名都长，靠 title 看全称） */
function CaseRow({ c, line, onJump }: { c: DealCase; line: DealCase[]; onJump: (caseId: number) => void }) {
  const multi = line.length > 1
  return (
    <button
      type="button"
      onClick={() => onJump(c.id)}
      title={'跳到 ' + c.name}
      className="flex w-full items-center gap-2.5 rounded-[8px] px-1.5 py-[5px] text-left transition-colors hover:bg-secondary"
    >
      <span className="flex min-w-[118px] flex-none items-center gap-[5px]">
        {line.map((l, i) => (
          <span key={l.id} className="flex items-center gap-[5px]">
            {i > 0 && <span className="text-[10px] text-border">→</span>}
            <StateDot state={l.done ? 'done' : 'cur'} size={multi ? 7 : 9} />
            <span
              className={
                'text-[11px] whitespace-nowrap ' +
                (l.id === c.id ? 'font-[620] text-foreground' : 'text-muted-foreground/70')
              }
            >
              {l.proc}
            </span>
          </span>
        ))}
      </span>
      <span className="min-w-0 flex-1 truncate text-[13px] font-[550] text-secondary-foreground">{c.name}</span>
      <span className="flex-none text-[11.5px] whitespace-nowrap text-muted-foreground/80">{c.auth}</span>
    </button>
  )
}
