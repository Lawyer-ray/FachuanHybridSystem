/**
 * 同题双答的并排渲染：一轮里两条 assistant 回答各占一栏，栏头标 agent 名。
 *
 * 为什么单独一个组件而不是在 MessageList 里开分支：MessageList 已接近软红线
 * （350 行），双栏的栏头/分隔/窄屏堆叠各是一段布局，塞进去会把气泡逻辑挤散。
 *
 * 宽度约定：`sm` 以上左右并排（律师在宽面板里并排对照两份意见），窄屏上下堆叠
 * ——侧边栏面板在笔记本上只有 400px 宽，硬塞两列会把每栏压成一行三个字的薯条。
 */

import { memo } from 'react'

import { agentLabel } from '../domain'
import type { ChatMessage } from '../types'

/** 栏头：小而克制的标签，两栏视觉上必须能一眼分清谁是谁 */
const LABEL_CLASS =
  'mb-1 inline-flex items-center rounded-[6px] border border-border bg-secondary/60 px-1.5 py-0.5 text-[11px] text-muted-foreground'

export const DualAnswers = memo(function DualAnswers({
  answers,
  renderAnswer,
}: {
  answers: ChatMessage[]
  /** 复用 MessageList 的 Bubble（它带了 Markdown / 平滑放字 / 复制按钮全套） */
  renderAnswer: (message: ChatMessage) => React.ReactNode
}) {
  return (
    <div className="grid gap-2 sm:grid-cols-2" data-testid="dual-answers">
      {answers.map((answer) => (
        <section key={answer.id} className="min-w-0" data-testid={`dual-column-${answer.agentKind ?? 'pi'}`}>
          <div className={LABEL_CLASS}>{agentLabel(answer.agentKind ?? '')}</div>
          {renderAnswer(answer)}
        </section>
      ))}
    </div>
  )
})
