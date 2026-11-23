/**
 * 「生成综合结论」工具条右侧的三项设置：执行 agent / 模型 / 先评审。
 *
 * 从 `ReviewPanel` 拆出（后者单函数超软红线）。本组件只渲染设置项，不取数、也不判断
 * 「能不能跑」——那是主按钮那边的事（`synthesisBlockedReason`）。三项共用一个
 * `disabled`（综合在跑时都不能改），所以收成一个 prop 而不是各传各的。
 */

import { agentLabel } from '../../domain'

/** 设置项外壳：把「标签 + 下拉」收成一个整体，避免裸 select 与裸文字混排。 */
const FIELD_SHELL_CLASS =
  'inline-flex items-center gap-1.5 rounded-md border border-border/60 bg-background px-1.5 py-0.5'

const SELECT_CLASS =
  'appearance-none bg-transparent pr-3.5 text-[12px] text-foreground outline-none ' +
  'disabled:cursor-not-allowed disabled:opacity-60'

/**
 * 不能跑综合的运行时：综合要求隔离运行（不读写该会话的历史），dsh 会把历史续写到
 * 磁盘且没有删除会话的接口，后端对它直接报错（见 ``dsh_backend`` 的 isolated 分支）。
 * 不放进下拉框，免得律师选了必然失败的一项。
 */
const SYNTHESIS_UNSUPPORTED_KINDS = new Set(['dsh'])

/** 「执行」下拉的选项：本轮各栏 + pi（去重，排掉不支持隔离运行的） */
function synthesisKindOptions(agents: readonly string[]): string[] {
  return [...new Set([...agents, 'pi'])].filter((kind) => !SYNTHESIS_UNSUPPORTED_KINDS.has(kind))
}

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

export function SynthesisControls({
  agents,
  kind,
  onKindChange,
  models,
  model,
  onModelChange,
  withReview,
  onWithReviewChange,
  disabled,
}: {
  /** 本轮的栏（`agent_kind`，顺序 = 请求顺序）：执行下拉的候选来源 */
  agents: readonly string[]
  /** 用哪个 agent 跑综合 */
  kind: string
  onKindChange: (kind: string) => void
  /** 所选执行 agent 的模型清单（null = 还没取到） */
  models: readonly string[] | null
  /** 选中的模型；空串 = 交给后端按本轮各栏解析 */
  model: string
  onModelChange: (model: string) => void
  /** 是否先跑一轮 rubric 评审（综合的第一步） */
  withReview: boolean
  onWithReviewChange: (withReview: boolean) => void
  /** 综合在跑：三项都不能改（本轮已开跑，改了只会与已提交的参数对不上） */
  disabled: boolean
}) {
  return (
    // 右侧设置项：执行 agent / 模型 / 先评审。窄屏时整体换行到下一行。
    <div className="ml-auto flex flex-wrap items-center gap-x-2 gap-y-1.5">
      {/* 用哪个 agent 跑综合：选项来自本轮各栏 + pi。
          选 agent 而不是"选模型"是有意的——agent 决定它能不能调工具去核引用。 */}
      <label className={FIELD_SHELL_CLASS} title="用哪个 agent 运行时来生成综合结论">
        <span className="text-[11px] text-muted-foreground">执行</span>
        <span className="relative inline-flex items-center">
          <select
            data-testid="synthesis-kind"
            value={kind}
            disabled={disabled}
            onChange={(event) => onKindChange(event.target.value)}
            className={SELECT_CLASS}
          >
            {synthesisKindOptions(agents).map((option) => (
              <option key={option} value={option}>
                {agentLabel(option)}
              </option>
            ))}
          </select>
          <Chevron />
        </span>
      </label>

      {/* 模型清单跟随所选执行 agent（口径在后端 /agent/backends 的 models，见
          use-review-actions 的 synthesisModelsFor）：换 agent 后原模型不能用就自动换。
          留「自动」是为了允许"交给后端按本轮各栏解析"，但默认已选中具体模型。 */}
      <label className={FIELD_SHELL_CLASS} title="用哪个模型生成综合结论；「自动」= 按本轮各栏的模型解析">
        <span className="text-[11px] text-muted-foreground">模型</span>
        <span className="relative inline-flex items-center">
          <select
            data-testid="synthesis-model"
            value={model}
            disabled={disabled}
            onChange={(event) => onModelChange(event.target.value)}
            className={SELECT_CLASS}
          >
            <option value="">自动</option>
            {(models ?? []).map((option) => (
              <option key={option} value={option}>
                {option}
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
          checked={withReview}
          disabled={disabled}
          onChange={(event) => onWithReviewChange(event.target.checked)}
          className="size-3.5 accent-foreground"
        />
        先评审
        <span className="text-[11px] text-muted-foreground/70">≈5 万 token</span>
      </label>
    </div>
  )
}
