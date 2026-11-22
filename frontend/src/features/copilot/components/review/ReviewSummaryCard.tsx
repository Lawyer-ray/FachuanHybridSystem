/**
 * 多答裁决汇总卡：一句 headline + 每栏 one_line + 共识/分歧（成团）+ 分歧点
 * （两侧原句并排）+ 点分数展开的逐条证据 + 采纳条。
 *
 * ## 为什么放在多答栏下方而不是上方
 *
 * headline 是**导航**而不是结论：读之前放一句「pi 栏多数通过」会先入为主，读之后
 * 放才是「我刚才看到的分歧，原来是这几条 rubric」。采纳也必须发生在读完答案之后。
 *
 * ## 什么不许做
 *
 * - **不给任何一栏加"推荐/最优"高亮或排序**：本批是影子模式，`tie` 语义也要求
 *   没有可判定代表时并排呈现各立场（见 domain/fusion 的 `toClusterViews`）；
 * - **`score === null` 显示「无有效判定」而不是 0%**：null = 一条有效票都没有，
 *   写成 0% 等于把"judge 没判出来"说成"全错"；
 * - 判不了的条目在证据里带原因（超时/解析失败/协议偏离可信度完全不同）。
 *
 * ## 无数据整块不渲染
 *
 * 由调用方（`useReview` 返回 null）保证；本组件只在有评审时挂载，所以不处理空态
 * ——空卡会让律师以为"评审跑了但什么都没说"。
 */

import { useState } from 'react'

import type { ReviewView } from '../../domain'
import { AdoptBar } from './AdoptBar'
import { ConflictPair } from './ConflictPair'
import { ConsensusList } from './ConsensusList'
import { EvidenceList } from './EvidenceList'

export function ReviewSummaryCard({ review }: { review: ReviewView }) {
  // 展开哪一栏的证据：一次只开一栏，几栏同时展开会把卡片拉成一整屏
  const [openLane, setOpenLane] = useState<string | null>(null)

  return (
    // 默认折叠：评审一展开就是四栏打分 + 共识/分歧 + 逐条分歧原文，常常占掉一整屏。
    // 律师关心的是"结论和哪栏更靠谱"，细节按需展开即可（<details> 原生支持键盘与读屏，
    // 不自己造展开状态）。
    <details
      data-testid="review-summary"
      aria-label="多答评审"
      className="group mt-2 min-w-0 rounded-[8px] border border-border bg-secondary/30 px-2 py-1.5 text-xs"
    >
      <summary className="flex min-w-0 cursor-pointer list-none items-center gap-1.5 [&::-webkit-details-marker]:hidden">
        <span className="flex-none font-medium">评审</span>
        <span data-testid="review-headline" className="min-w-0 flex-1 truncate text-muted-foreground">
          {review.headline || '本轮评审没有给出一句话结论'}
        </span>
        {/* 折叠态也给出每栏分数：一眼就能看出"哪栏被扣分了"，不用展开 */}
        <span className="hidden flex-none items-center gap-1 sm:flex">
          {review.lanes.map((lane) => (
            <span
              key={lane.lane}
              data-testid={`review-badge-${lane.lane}`}
              className="rounded-full bg-background px-1.5 py-px text-[10px] tabular-nums text-muted-foreground"
              title={`${lane.label}：${lane.score === null ? '无有效判定' : `${Math.round(lane.score * 100)}%`}`}
            >
              {lane.label} {lane.score === null ? '—' : `${Math.round(lane.score * 100)}%`}
            </span>
          ))}
        </span>
        <svg
          aria-hidden="true"
          viewBox="0 0 12 12"
          className="size-3 flex-none text-muted-foreground transition-transform group-open:rotate-180"
        >
          <path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </svg>
      </summary>

      {review.stage === 'shadow' && (
        <p
          className="mt-1 text-[10px] text-muted-foreground"
          title="影子模式：评审与采纳都只展示/留痕，不触发任何自动动作"
        >
          影子模式：评审与采纳只展示/留痕，不触发任何自动动作
        </p>
      )}

      <ul className="mt-1.5 space-y-1">
        {review.lanes.map((lane) => {
          const open = openLane === lane.lane
          return (
            <li key={lane.lane} className="min-w-0" data-testid={`review-lane-${lane.lane}`}>
              <div className="flex min-w-0 items-baseline gap-2">
                <span className="flex-none font-medium">{lane.label}</span>
                <span className="min-w-0 flex-1 truncate text-muted-foreground" title={lane.oneLine}>
                  {lane.oneLine}
                </span>
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => setOpenLane(open ? null : lane.lane)}
                  title="点开看逐条 rubric 判定与 judge 引用的原文"
                  data-testid={`lane-score-${lane.lane}`}
                  className="flex-none rounded-[4px] px-1 text-[11px] tabular-nums text-foreground/80 transition-colors hover:bg-secondary"
                >
                  {lane.score === null ? '无有效判定' : `${Math.round(lane.score * 100)}%`}
                </button>
              </div>
              {open && (
                <EvidenceList
                  verdicts={review.verdicts.filter((verdict) => verdict.lane === lane.lane)}
                  laneLabel={lane.label}
                />
              )}
            </li>
          )
        })}
      </ul>

      {/* 成团：谁和谁是同一个立场。失败只显示原因，不折算成「三份全异」（见 ConsensusList） */}
      <ConsensusList clusters={review.clusters} clustersError={review.clustersError} />

      {review.conflicts.length > 0 && (
        <div className="mt-2" data-testid="review-conflicts">
          <div className="text-[11px] font-medium text-muted-foreground">分歧点（同一条 rubric 各栏判断相反）</div>
          <ul className="mt-1 space-y-1.5">
            {review.conflicts.map((pair) => (
              <ConflictPair key={pair.rubricId} pair={pair} />
            ))}
          </ul>
        </div>
      )}

      <AdoptBar reviewId={review.reviewId} lanes={review.lanes} />
    </details>
  )
}
