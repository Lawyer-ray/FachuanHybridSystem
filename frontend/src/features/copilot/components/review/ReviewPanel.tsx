/**
 * 一轮多答下方的「评审 / 综合结论」入口：无评审时给按钮，有评审时挂卡、再给合成按钮，
 * 有合成记录时挂综合结论卡。
 *
 * ## 按钮顺序就是阅读顺序
 *
 * 评审卡（打分 + 共识/分歧）先出现，综合结论按钮在**它下面**：先看「哪栏更好」，
 * 再决定要不要花钱把几栏收敛成一份稿。两个动作都只能由点击触发——一轮三栏评审
 * 约 5 万 token，自动跑等于替律师决定花钱（见 `use-review-actions`）。
 *
 * ## 为什么单独成组件
 *
 * `MultiAnswers` 是流式热路径上的 memo 边界（每个 delta 都会重渲），新增的请求
 * 状态/按钮/卡片一律留在本组件里，那条边界只多一个子节点。评审与合成互不依赖：
 * 刷新页面时若只有历史合成记录（没跑评审），综合结论卡照样要显示出来。
 */

import { useReviewActions } from './use-review-actions'
import { ReviewSummaryCard } from './ReviewSummaryCard'
import { SynthesisCard } from './SynthesisCard'

const ACTION_BUTTON_CLASS =
  'flex-none rounded-[4px] border border-border bg-background px-1.5 py-0.5 text-[11px] text-foreground/80 transition-colors hover:bg-secondary disabled:cursor-not-allowed disabled:opacity-50'

export function ReviewPanel({
  target,
  agents,
}: {
  /**
   * 这一轮的评审数据源（`null` = 不挂面板）。
   *
   * `turn` 必须由调用方按「后端口径 + 窗口完整」算出来（见 domain/fusion 的
   * `reviewTurnOf`）：算不出正确轮次时宁可整块不渲染，也不要把别轮的评审挂到
   * 这一轮的答案下面。
   */
  target: { sessionId: string; turn: number } | null
  /** 本轮的栏（`agent_kind`，顺序 = 请求顺序）；调用方必须传稳定引用 */
  agents: readonly string[]
}) {
  const actions = useReviewActions(target?.sessionId ?? null, target?.turn ?? null, agents)
  if (!target) return null

  // 只有**明确**拿到空清单才禁用：null = 还没取到/取失败，judge_models 允许为空，
  // 由服务端按配置或本轮栏模型解析。
  const modelsMissing = actions.judgeModels !== null && actions.judgeModels.length === 0

  return (
    <div className="mt-2 min-w-0 space-y-2" data-testid="review-panel">
      {actions.review ? (
        <ReviewSummaryCard review={actions.review} />
      ) : (
        <div className="flex flex-wrap items-center gap-1.5" data-testid="review-start">
          <button
            type="button"
            disabled={actions.reviewRunning || modelsMissing}
            onClick={actions.startReview}
            className={ACTION_BUTTON_CLASS}
          >
            {actions.reviewRunning ? '评审中…' : '评审'}
          </button>
          <span className="text-[11px] text-muted-foreground">
            {modelsMissing
              ? '平台无可用评审模型，暂时不能跑评审'
              : '对这几栏跑一轮 rubric 评审（一轮三栏约 5 万 token，点了才跑）'}
          </span>
        </div>
      )}

      {/* 综合结论按钮只在评审卡之后出现：先看打分与共识/分歧，再决定要不要合成 */}
      {actions.review && (
        <div className="flex flex-wrap items-center gap-1.5" data-testid="synthesis-start">
          <button
            type="button"
            disabled={actions.synthesisRunning}
            onClick={actions.startSynthesis}
            className={ACTION_BUTTON_CLASS}
          >
            {actions.synthesisRunning ? '生成中…' : actions.synthesis ? '重新生成综合结论' : '综合结论'}
          </button>
          <span className="text-[11px] text-muted-foreground">把各栏收敛成一份合成稿（来源可追溯，点了才跑）</span>
        </div>
      )}

      {actions.synthesis && <SynthesisCard synthesis={actions.synthesis} />}
    </div>
  )
}
