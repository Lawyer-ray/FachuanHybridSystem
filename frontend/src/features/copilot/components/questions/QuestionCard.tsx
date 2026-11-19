/**
 * 结构化提问卡：模型反问（`question_request`）的作答界面。
 *
 * 与审批卡同层并列（转录下方独立队列），**不内嵌进消息流**——提问会阻塞服务端
 * 等待，任何会随消息滚走的位置都会让律师「根本看不到 AI 在问什么」，然后 180s
 * 后模型按假设继续（法律场景等于编事实）。
 *
 * 一题一屏（1/N 分页）：模型一次最多问 4 题（后端 MAX_QUESTIONS），
 * 全部平铺会把面板撑爆；分页也让「上一题还能改」这件事成立（草稿在 store 里，
 * 翻页不丢）。
 */

import { useState } from 'react'
import { MessageCircleQuestion, SkipForward, X } from 'lucide-react'

import { Button } from '@/components/ui/button'

import { emptyDraft, isAnswered, setFreeform, toggleSelection } from '../../domain'
import { useCopilot } from '../../store'
import { draftKey } from '../../store/question'
import type { PendingQuestion, QuestionItem } from '../../types'
import { QuestionCountdown } from './QuestionCountdown'

/** 选项一行（单选=radio 语义、多选=checkbox 语义；aria 让读屏能听懂） */
function OptionButton({
  item,
  label,
  description,
  selected,
  disabled,
  onClick,
}: {
  item: QuestionItem
  label: string
  description: string
  selected: boolean
  disabled: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      role={item.allowMultiple ? 'checkbox' : 'radio'}
      aria-checked={selected}
      disabled={disabled}
      onClick={onClick}
      className={`w-full rounded-[8px] border px-2.5 py-2 text-left transition-colors disabled:opacity-60 ${
        selected
          ? 'border-primary/60 bg-primary/10'
          : 'border-border hover:bg-secondary'
      }`}
    >
      <span className="block text-[13px] font-medium">{label}</span>
      {description && (
        <span className="mt-0.5 block text-[11px] leading-relaxed text-muted-foreground">
          {description}
        </span>
      )}
    </button>
  )
}

export function QuestionCard({ question }: { question: PendingQuestion }) {
  const drafts = useCopilot((s) => s.questionDrafts)
  const setQuestionDraft = useCopilot((s) => s.setQuestionDraft)
  const submitQuestion = useCopilot((s) => s.submitQuestion)
  const dismissQuestion = useCopilot((s) => s.dismissQuestion)
  const [index, setIndex] = useState(0)

  const total = question.questions.length
  const current = question.questions[Math.min(index, total - 1)]!
  const draft = drafts[draftKey(question.questionId, current.id)] ?? emptyDraft()
  const locked = question.submitting === true || question.submitted !== undefined
  const done = question.submitted !== undefined
  const answeredAll = question.questions.filter((q) =>
    isAnswered(drafts[draftKey(question.questionId, q.id)]),
  ).length

  const write = (next: typeof draft) => setQuestionDraft(question.questionId, current.id, next)
  const isLast = index >= total - 1

  return (
    <div className="rounded-[10px] border border-primary/40 bg-primary/5 px-3 py-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          <MessageCircleQuestion className="size-3.5 shrink-0 text-primary" aria-hidden />
          <span className="text-[12px] font-medium">AI 需要你确认</span>
          {question.agentKind && (
            <span className="rounded-[4px] bg-secondary px-1 py-0.5 text-[10px] text-muted-foreground">
              {question.agentKind}
            </span>
          )}
          {total > 1 && (
            <span className="text-[11px] text-muted-foreground tabular-nums">
              {index + 1} / {total}
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <QuestionCountdown
            timeoutSeconds={question.timeoutSeconds}
            receivedAt={question.receivedAt}
            frozen={done}
          />
          <button
            type="button"
            title={done ? '关闭' : '关闭（模型到点会按假设继续）'}
            className="rounded p-0.5 text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            onClick={() => dismissQuestion(question.questionId)}
          >
            <X className="size-3.5" aria-hidden />
          </button>
        </div>
      </div>

      <p className="mt-2 text-[13px] font-medium leading-relaxed">{current.question}</p>
      {current.context && (
        <p className="mt-1 max-h-24 overflow-y-auto whitespace-pre-wrap rounded-[6px] bg-background/60 px-2 py-1 text-[11px] leading-relaxed text-muted-foreground">
          {current.context}
        </p>
      )}

      {current.options.length > 0 && (
        <div className="mt-2 flex flex-col gap-1.5" role="group" aria-label="可选答案">
          {current.options.map((opt) => (
            <OptionButton
              key={opt.label}
              item={current}
              label={opt.label}
              description={opt.description}
              selected={draft.selections.includes(opt.label)}
              disabled={locked}
              onClick={() => write(toggleSelection(current, draft, opt.label))}
            />
          ))}
        </div>
      )}

      {current.allowFreeform && (
        <textarea
          value={draft.text}
          disabled={locked}
          rows={2}
          placeholder={current.options.length > 0 ? '以上都不合适？直接写你的答案…' : '写下你的答案…'}
          className="mt-2 w-full resize-y rounded-[8px] border border-border bg-background px-2 py-1.5 text-[12px] leading-relaxed outline-none focus:border-primary/60 disabled:opacity-60"
          onChange={(e) => write(setFreeform(current, draft, e.target.value))}
        />
      )}

      {current.allowComment && (
        <input
          value={draft.comment}
          disabled={locked}
          placeholder="备注（可选）"
          className="mt-1.5 w-full rounded-[8px] border border-border bg-background px-2 py-1.5 text-[12px] outline-none focus:border-primary/60 disabled:opacity-60"
          onChange={(e) => write({ ...draft, comment: e.target.value })}
        />
      )}

      <div className="mt-2 flex items-center justify-between gap-2">
        <span className="text-[11px] text-muted-foreground">
          {done
            ? (question.note ??
              (question.submitted === 'skipped' ? '已跳过，本轮按假设继续' : '已回答'))
            : total > 1
              ? `已答 ${answeredAll} / ${total}`
              : ''}
        </span>
        <div className="flex items-center gap-1.5">
          {!done && total > 1 && index > 0 && (
            <Button variant="ghost" size="sm" className="h-7 px-2 text-[12px]" onClick={() => setIndex(index - 1)}>
              上一题
            </Button>
          )}
          {!done && total > 1 && !isLast && (
            <Button variant="outline" size="sm" className="h-7 px-2 text-[12px]" onClick={() => setIndex(index + 1)}>
              下一题
            </Button>
          )}
          {!done && (
            <>
              <Button
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-[12px] text-muted-foreground"
                disabled={question.submitting === true}
                title="跳过整组：模型会按现有信息继续并说明假设"
                onClick={() => void submitQuestion(question.questionId)}
              >
                <SkipForward className="mr-1 size-3" aria-hidden />
                跳过
              </Button>
              <Button
                size="sm"
                className="h-7 px-2.5 text-[12px]"
                disabled={question.submitting === true}
                onClick={() => void submitQuestion(question.questionId)}
              >
                {question.submitting ? '提交中…' : '提交'}
              </Button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
