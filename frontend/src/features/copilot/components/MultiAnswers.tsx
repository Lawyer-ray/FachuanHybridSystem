/**
 * 多答（multi-agent answers）的并排渲染：一轮里 2~MAX_ANSWERS 条 assistant 回答
 * 各占一栏，栏头标 agent 名。单栏不走这里（调用方直接渲染普通气泡，见
 * MessageList 的 groupAnswerRuns 分支）——单栏套一层分栏容器会在视觉上暗示
 * 「本来可以有几栏」，那是引入多答之前没有的体验。
 *
 * 为什么单独一个组件而不是在 MessageList 里开分支：MessageList 已接近软红线
 * （350 行），栏头/分隔/窄屏堆叠各是一段布局，塞进去会把气泡逻辑挤散。
 *
 * 为什么改造而不是新建：旧名字是 `DualAnswers`，但它本来就只是「把 N 条回答
 * 并排」——含 `Dual` 的只有名字和写死的 `sm:grid-cols-2`，两处都随多答一起改；
 * 另起一个 MultiAnswers 只会留下一个没人用的 DualAnswers。
 *
 * 宽度约定：`sm` 以上并排（律师在宽面板里并排对照几份意见），窄屏上下堆叠
 * ——侧边栏面板在笔记本上只有 400px 宽，硬塞四列会把每栏压成一行三个字的薯条。
 */

import { memo } from 'react'

import { agentLabel } from '../domain'
import type { AgentBackendOption, ChatMessage } from '../types'
import { findBackend, noApprovalWarn } from '../store/backends'
import { LaneFactsBadge } from './LaneFactsBadge'
import { LaneUsageChip } from './LaneUsageChip'
import { NoApprovalBadge } from './NoApprovalBadge'

/** 栏头：小而克制的标签，各栏视觉上必须能一眼分清谁是谁（以及用哪个模型答的） */
const LABEL_CLASS =
  'mb-1 inline-flex min-w-0 items-center rounded-[6px] border border-border bg-secondary/60 px-1.5 py-0.5 text-[11px] text-muted-foreground'

/**
 * 栏数 → 宽屏下的列数。
 *
 * 写死 `sm:grid-cols-2` 会把三、四栏硬塞成两列两行：同一轮的几份回答被折成
 * 「上面一对、下面一个」，对照关系就散了。Tailwind 只认字面量类名，所以这里
 * 枚举而不能拼字符串。
 */
const GRID_BY_COLUMNS: Record<number, string> = {
  2: 'sm:grid-cols-2',
  3: 'sm:grid-cols-3',
  4: 'sm:grid-cols-4',
}

/**
 * 栏头正文：「agent · 模型」。
 *
 * 模型这半截是**核心需求**而不是装饰：律师引入多答就是为了比较效果，只写 agent
 * 名的话，同一个 agent 换两个模型跑两栏会看起来像同一个人说了两遍不同的话。
 *
 * 模型名长（`claude-opus-4-5-20251101`）就把栏头撑垮，所以截断到 110px、
 * 悬停显示全名——按像素而非字符截断是因为字宽差异大（`1` vs `W`）。
 */
export function AgentModelHead({ label, model }: { label: string; model?: string }) {
  if (!model) return <>{label}</>
  return (
    <>
      <span className="truncate">{label}</span>
      <span className="mx-1 flex-none opacity-50" aria-hidden>
        ·
      </span>
      <span className="max-w-[110px] truncate" title={model} data-testid="column-model">
        {model}
      </span>
    </>
  )
}

export const MultiAnswers = memo(function MultiAnswers({
  answers,
  renderAnswer,
  highlightKind,
  backends = [],
}: {
  answers: ChatMessage[]
  /** 复用 MessageList 的 Bubble（它带了 Markdown / 平滑放字 / 复制按钮全套） */
  renderAnswer: (message: ChatMessage) => React.ReactNode
  /** 当前默认后端的高亮 kind（栏头加粗）；空串表示不高亮 */
  highlightKind?: string
  /**
   * 后端清单（只为读 `capabilities.approval`）：没有审批闸门的那一栏要在栏头说清。
   * 律师是**看完了回答**才决定采不采用的，栏头是他唯一会回看的位置。
   */
  backends?: AgentBackendOption[]
}) {
  const grid = GRID_BY_COLUMNS[answers.length] ?? GRID_BY_COLUMNS[4]
  return (
    <div className={`grid gap-2 ${grid}`} data-testid="multi-answers" data-columns={answers.length}>
      {answers.map((answer) => {
        const kind = answer.agentKind ?? ''
        const highlighted = Boolean(highlightKind) && kind === highlightKind
        return (
          <section key={answer.id} className="min-w-0" data-testid={`multi-column-${kind || 'pi'}`}>
            <div className="flex min-w-0 items-center gap-1">
              <div
                className={`${LABEL_CLASS} ${highlighted ? 'border-foreground/30 font-medium text-foreground' : ''}`}
                data-default={highlighted ? 'true' : undefined}
              >
                <AgentModelHead label={agentLabel(kind)} model={answer.model} />
              </div>
              {/* 这一栏没有人工审批闸门：高危工具不会弹卡（dsh 直接拒绝 / openai-agents 照常执行） */}
              {noApprovalWarn(findBackend(backends, kind)) && <NoApprovalBadge />}
              {/* 体检事实：读这条回答自己的引用/工具/截断标记，零数据时不渲染；
                  放在用量之前——用量文字长，把「没引/没查」挤到栏宽外就白做了 */}
              <LaneFactsBadge message={answer} />
              {/* 分栏用量：多答就是为了比较，栏头必须能看出谁贵谁快 */}
              {/* usage：历史轮次的落库用量；缺省时 chip 自己回落到本轮内存账 */}
              <LaneUsageChip kind={kind} usage={answer.laneUsage} />
            </div>
            {renderAnswer(answer)}
          </section>
        )
      })}
    </div>
  )
})
