/**
 * store slice：结构化提问（模型反问律师）。
 *
 * 为什么**不进 `messages`**：提问与审批一样是「打断当前流的交互」，必须与
 * 转录同层并列渲染（各自一个队列），否则会随消息滚走、也会污染转录与导出。
 * 面板收起再打开、切会话回来，待答问题要还在——所以草稿进 store 而不是组件
 * 本地 state（DSH 的 QuestionComposer 也是把草稿存进 session store 的）。
 *
 * 与审批的三处刻意差异：
 * - 无 fail-closed：超时 = 模型按假设继续，问题**不失效**，仍可补答；
 * - 无「必须在本轮内答完」：`loadPendingQuestions` 会在面板重开时补拉；
 * - 提交是幂等的：重复点只发一次（`submitting` 置忙），服务端按 question_id
 *   对齐答案，迟到提交会回 `accepted && !success` 而不是报错。
 */

import * as copilotApi from '../api'
import { buildAnswerBatch, normalizeQuestions } from '../domain'
import type { PendingQuestion, QuestionDraft } from '../types'
import type { CopilotState } from '../types'
import type { Slice } from './slice'

/** 后端默认等待窗口（services/question.py 的 DEFAULT_QUESTION_TIMEOUT=180s） */
export const DEFAULT_QUESTION_TIMEOUT_S = 180

/** 草稿键：一问一题的草稿彼此独立（同一 question_id 下可能有多题） */
export function draftKey(questionId: string, itemId: string): string {
  return `${questionId}:${itemId}`
}

export type QuestionSlice = Pick<
  CopilotState,
  | 'pendingQuestions'
  | 'questionDrafts'
  | 'enqueueQuestion'
  | 'setQuestionDraft'
  | 'submitQuestion'
  | 'dismissQuestion'
  | 'loadPendingQuestions'
>

export const createQuestionSlice: Slice<QuestionSlice> = (set, get) => ({
  pendingQuestions: [],
  questionDrafts: {},

  enqueueQuestion: (question) => {
    set((s) => {
      // 同一个 question_id 只留一份：重连/补拉/事件重放都可能再来一条
      if (s.pendingQuestions.some((q) => q.questionId === question.questionId)) return s
      return { pendingQuestions: [...s.pendingQuestions, question] }
    })
  },

  setQuestionDraft: (questionId, itemId, draft) => {
    set((s) => ({ questionDrafts: { ...s.questionDrafts, [draftKey(questionId, itemId)]: draft } }))
  },

  submitQuestion: async (questionId) => {
    const target = get().pendingQuestions.find((q) => q.questionId === questionId)
    if (!target || target.submitting || target.submitted) return

    const drafts: Record<string, QuestionDraft> = {}
    for (const item of target.questions) {
      const draft = get().questionDrafts[draftKey(questionId, item.id)]
      if (draft) drafts[item.id] = draft
    }
    const answers = buildAnswerBatch(target.questions, drafts)
    // 一道都没答：按「跳过」提交（与点「跳过」同一语义，后端会把缺项标 unanswered）
    const skipped = answers.length === 0

    set((s) => ({
      pendingQuestions: s.pendingQuestions.map((q) =>
        q.questionId === questionId ? { ...q, submitting: true, note: undefined } : q,
      ),
    }))

    try {
      const receipt = await copilotApi.answerQuestion(questionId, { answers, skipped })
      set((s) => ({
        pendingQuestions: s.pendingQuestions.map((q) =>
          q.questionId !== questionId
            ? q
            : {
                ...q,
                submitting: false,
                // 等待方已超时（模型已按假设继续）仍是「已提交」：答案被记录了，
                // 不能显示成失败让律师再点一次
                submitted: skipped ? 'skipped' : 'answered',
                continued: receipt.success === false,
                note: receipt.note || receipt.error,
              },
        ),
      }))
    } catch {
      // 网络/鉴权失败：保持可编辑可重提，不像审批那样静默吞掉（答案没送到就白问了）
      set((s) => ({
        pendingQuestions: s.pendingQuestions.map((q) =>
          q.questionId === questionId ? { ...q, submitting: false, note: '提交失败，请重试' } : q,
        ),
      }))
    }
  },

  dismissQuestion: (questionId) => {
    set((s) => {
      const nextDrafts = { ...s.questionDrafts }
      for (const key of Object.keys(nextDrafts)) {
        if (key.startsWith(`${questionId}:`)) delete nextDrafts[key]
      }
      return {
        pendingQuestions: s.pendingQuestions.filter((q) => q.questionId !== questionId),
        questionDrafts: nextDrafts,
      }
    })
  },

  loadPendingQuestions: async () => {
    try {
      const items = await copilotApi.fetchPendingQuestions()
      // 端点返回「当前律师全部会话」的待答提问：只收当前会话那份，
      // 否则别的会话的反问会渲染在本会话上（红队审查 F11）
      const sessionId = get().sessionId
      if (!sessionId) return
      const known = new Set(get().pendingQuestions.map((q) => q.questionId))
      const fresh: PendingQuestion[] = []
      for (const item of items) {
        if (known.has(item.question_id)) continue
        if (item.session_id !== sessionId) continue
        const questions = normalizeQuestions(item.questions)
        if (questions.length === 0) continue
        fresh.push({
          questionId: item.question_id,
          sessionId,
          questions,
          timeoutSeconds: DEFAULT_QUESTION_TIMEOUT_S,
          // 倒计时按服务端创建时刻起算：补拉回来的卡可能已经等了一会儿
          receivedAt: Date.parse(item.created_at) || Date.now(),
        })
      }
      if (fresh.length > 0) set((s) => ({ pendingQuestions: [...s.pendingQuestions, ...fresh] }))
    } catch {
      // 补拉失败不阻塞主流程（面板下次打开会再试）
    }
  },
})
