/**
 * 一轮多答下方的**唯一入口**：「生成综合结论」工具条 + 评审卡 + 综合结论卡。
 *
 * ## 一个按钮，评审是它的第一步
 *
 * 不再有独立的「评审」按钮：打分只是综合的一个步骤（业务方口径）。工具条右侧是这次
 * 综合的三个参数——执行 agent / 模型 / 是否先评审（默认勾）。评审卡与综合卡**有就
 * 渲染**，不参与"能不能点"的判断（历史轮次只有其中一张的情况很常见）。
 *
 * 一切都只能由点击触发：一轮评审约 5 万 token，自动跑等于替律师决定花钱
 * （见 `use-review-actions`）。
 *
 * ## 为什么单独成组件
 *
 * `MultiAnswers` 是流式热路径上的 memo 边界（每个 delta 都会重渲），新增的请求
 * 状态/按钮/卡片一律留在本组件里，那条边界只多一个子节点。评审与合成互不依赖：
 * 刷新页面时若只有历史合成记录（没跑评审），综合结论卡照样要显示出来。
 */

import { agentLabel } from '../../domain'

import { useReviewActions } from './use-review-actions'
import { ReviewSummaryCard } from './ReviewSummaryCard'
import { SynthesisCard } from './SynthesisCard'

/** 主操作：实心深色，视觉上必须压过右侧那排设置项（它是这一栏唯一花钱的按钮）。 */
const PRIMARY_BUTTON_CLASS =
  'inline-flex flex-none items-center gap-1.5 rounded-md bg-foreground px-2.5 py-1.5 text-[12px] font-medium ' +
  'text-background shadow-sm transition-opacity hover:opacity-90 ' +
  'disabled:cursor-not-allowed disabled:opacity-50'

/** 设置项外壳：把「标签 + 下拉」收成一个整体，避免裸 select 与裸文字混排。 */
const FIELD_SHELL_CLASS =
  'inline-flex items-center gap-1.5 rounded-md border border-border/60 bg-background px-1.5 py-0.5'

const SELECT_CLASS =
  'appearance-none bg-transparent pr-3.5 text-[12px] text-foreground outline-none ' +
  'disabled:cursor-not-allowed disabled:opacity-60'


function Chevron() {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 12 12"
      className="pointer-events-none absolute right-1 size-3 text-muted-foreground"
    >
      <path d="M3 4.5 6 7.5 9 4.5" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
    </svg>
  )
}


function Sparkle() {
  return (
    <svg aria-hidden="true" viewBox="0 0 16 16" className="size-3.5">
      <path
        d="M8 1.5 9.4 6 14 7.4 9.4 8.8 8 13.3 6.6 8.8 2 7.4 6.6 6 8 1.5Z"
        fill="currentColor"
        opacity="0.9"
      />
    </svg>
  )
}

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
      {/* 只有一个入口：「生成综合结论」。评审是它的**第一步**（默认勾选），
          不是需要人先点一次的独立动作——业务方口径：打分只是综合的一个步骤。
          评审卡有就展示（历史轮次 / 综合后回读），没有也不影响点按钮。 */}
      <div
        className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border border-border/60 bg-secondary/40 px-2.5 py-2"
        data-testid="synthesis-start"
      >
        <button
          type="button"
          disabled={actions.synthesisRunning}
          onClick={actions.startSynthesis}
          className={PRIMARY_BUTTON_CLASS}
        >
          <Sparkle />
          {actions.synthesisRunning ? '生成中…' : actions.synthesis ? '重新生成' : '生成综合结论'}
        </button>

        {/* 右侧设置项：执行 agent / 模型 / 先评审。窄屏时整体换行到下一行。 */}
        <div className="ml-auto flex flex-wrap items-center gap-x-2 gap-y-1.5">
          {/* 用哪个 agent 跑综合：选项来自本轮各栏 + pi。
              选 agent 而不是"选模型"是有意的——agent 决定它能不能调工具去核引用。 */}
          <label className={FIELD_SHELL_CLASS} title="用哪个 agent 运行时来生成综合结论">
            <span className="text-[11px] text-muted-foreground">执行</span>
            <span className="relative inline-flex items-center">
              <select
                data-testid="synthesis-kind"
                value={actions.synthesisKind}
                disabled={actions.synthesisRunning}
                onChange={(event) => actions.setSynthesisKind(event.target.value)}
                className={SELECT_CLASS}
              >
                {[...new Set([...agents, 'pi'])].map((kind) => (
                  <option key={kind} value={kind}>
                    {agentLabel(kind)}
                  </option>
                ))}
              </select>
              <Chevron />
            </span>
          </label>

          {/* 模型清单与评审共用平台模型列表：两者都是"平台上有哪些模型"，各拉一份迟早漂移。
              留「自动」是为了允许"交给后端按本轮各栏解析"，但默认已选中具体模型。 */}
          <label className={FIELD_SHELL_CLASS} title="用哪个模型生成综合结论；「自动」= 按本轮各栏的模型解析">
            <span className="text-[11px] text-muted-foreground">模型</span>
            <span className="relative inline-flex items-center">
              <select
                data-testid="synthesis-model"
                value={actions.synthesisModel}
                disabled={actions.synthesisRunning}
                onChange={(event) => actions.setSynthesisModel(event.target.value)}
                className={SELECT_CLASS}
              >
                <option value="">自动</option>
                {(actions.judgeModels ?? []).map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
              <Chevron />
            </span>
          </label>

          <label
            className="inline-flex items-center gap-1.5 text-[12px] text-muted-foreground"
            title="先跑一轮 rubric 评审（5 栏 × judge，约 5 万 token），把得分与共识/分歧作为综合的取舍依据"
          >
            <input
              type="checkbox"
              data-testid="synthesis-with-review"
              checked={actions.synthesisWithReview}
              disabled={actions.synthesisRunning}
              onChange={(event) => actions.setSynthesisWithReview(event.target.checked)}
              className="size-3.5 accent-foreground"
            />
            先评审
            <span className="text-[11px] text-muted-foreground/70">≈5 万 token</span>
          </label>
        </div>
      </div>

      {modelsMissing && actions.synthesisWithReview && (
        <p className="text-[11px] text-amber-600 dark:text-amber-500" data-testid="review-models-missing">
          平台无可用评审模型，本次会跳过评审直接综合
        </p>
      )}

      {actions.review && <ReviewSummaryCard review={actions.review} />}
      {actions.synthesis && <SynthesisCard synthesis={actions.synthesis} />}
    </div>
  )
}
