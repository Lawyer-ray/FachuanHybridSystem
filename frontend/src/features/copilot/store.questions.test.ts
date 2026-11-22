import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from './api'
import { useCopilot } from './store'

vi.mock('./api', () => ({
  createSession: vi.fn(),
  fetchHistory: vi.fn(),
  openMessageStream: vi.fn(),
  decideApproval: vi.fn(),
  listSessions: vi.fn(),
  deleteSession: vi.fn(),
  steerSession: vi.fn(),
  clearSessionQueue: vi.fn(),
  submitAgentTask: vi.fn(),
  fetchPendingApprovals: vi.fn(),
  uploadAttachment: vi.fn(),
  answerQuestion: vi.fn(),
  fetchPendingQuestions: vi.fn(),
}))

/** 一道单选 + 一道多选的题组 */
const QUESTIONS = [
  {
    id: 'q1',
    question: '以哪份合同为准？',
    context: '第三条：…',
    options: [{ label: '甲合同', description: '' }],
    allow_freeform: true,
    allow_multiple: false,
    allow_comment: false,
  },
  {
    id: 'q2',
    question: '需要补哪些条款？',
    options: [{ label: '违约责任', description: '' }],
    allow_freeform: true,
    allow_multiple: true,
    allow_comment: true,
  },
]

const question = () => ({
  questionId: 'qq-1',
  sessionId: 's-1',
  questions: QUESTIONS.map((q) => ({
    id: q.id,
    question: q.question,
    context: q.context ?? '',
    options: q.options,
    allowFreeform: q.allow_freeform,
    allowMultiple: q.allow_multiple,
    allowComment: q.allow_comment,
  })),
  timeoutSeconds: 180,
  receivedAt: Date.now(),
})

beforeEach(() => {
  vi.clearAllMocks()
  useCopilot.getState().reset()
  useCopilot.setState({ sessionId: 's-1' })
})

describe('copilot store：结构化提问', () => {
  it('同一个 question_id 只入队一次（重连/事件重放不重复出卡）', () => {
    const q = question()
    useCopilot.getState().enqueueQuestion(q)
    useCopilot.getState().enqueueQuestion(q)
    expect(useCopilot.getState().pendingQuestions).toHaveLength(1)
  })

  it('提交时按 id 回填草稿，只带已作答的题', async () => {
    vi.mocked(copilotApi.answerQuestion).mockResolvedValue({ success: true, accepted: true })
    useCopilot.getState().enqueueQuestion(question())
    useCopilot.getState().setQuestionDraft('qq-1', 'q1', { selections: ['甲合同'], text: '', comment: '' })

    await useCopilot.getState().submitQuestion('qq-1')

    expect(copilotApi.answerQuestion).toHaveBeenCalledWith('qq-1', {
      answers: [{ id: 'q1', selections: ['甲合同'], text: '', comment: '' }],
      skipped: false,
    })
    const card = useCopilot.getState().pendingQuestions[0]!
    expect(card.submitted).toBe('answered')
    expect(card.submitting).toBe(false)
  })

  it('一道未答就提交 = 跳过整组（answers 为空、skipped=true）', async () => {
    vi.mocked(copilotApi.answerQuestion).mockResolvedValue({ success: true, accepted: true })
    useCopilot.getState().enqueueQuestion(question())

    await useCopilot.getState().submitQuestion('qq-1')

    expect(copilotApi.answerQuestion).toHaveBeenCalledWith('qq-1', { answers: [], skipped: true })
    expect(useCopilot.getState().pendingQuestions[0]!.submitted).toBe('skipped')
  })

  it('服务端已超时（success=false）仍是「已提交」，提示本轮已继续', async () => {
    vi.mocked(copilotApi.answerQuestion).mockResolvedValue({
      success: false,
      accepted: true,
      note: '回答已记录，但本轮对话已按超时继续',
    })
    useCopilot.getState().enqueueQuestion(question())
    useCopilot.getState().setQuestionDraft('qq-1', 'q1', { selections: ['甲合同'], text: '', comment: '' })

    await useCopilot.getState().submitQuestion('qq-1')

    const card = useCopilot.getState().pendingQuestions[0]!
    expect(card.continued).toBe(true)
    expect(card.note).toContain('已按超时继续')
  })

  it('提交失败保持可重提（不像审批那样静默吞掉）', async () => {
    vi.mocked(copilotApi.answerQuestion).mockRejectedValue(new Error('502'))
    useCopilot.getState().enqueueQuestion(question())

    await useCopilot.getState().submitQuestion('qq-1')

    const card = useCopilot.getState().pendingQuestions[0]!
    expect(card.submitted).toBeUndefined()
    expect(card.submitting).toBe(false)
    expect(card.note).toBe('提交失败，请重试')
  })

  it('补拉只收当前会话的提问（别的会话的反问不能串过来）', async () => {
    vi.mocked(copilotApi.fetchPendingQuestions).mockResolvedValue([
      {
        question_id: 'mine',
        session_id: 's-1',
        questions: [QUESTIONS[0]!],
        created_at: new Date().toISOString(),
      },
      {
        question_id: 'other',
        session_id: 's-2',
        questions: [QUESTIONS[1]!],
        created_at: new Date().toISOString(),
      },
    ])

    await useCopilot.getState().loadPendingQuestions()

    expect(useCopilot.getState().pendingQuestions.map((q) => q.questionId)).toEqual(['mine'])
  })

  it('补拉时题面无法解析的条目直接丢弃（不占交互席位）', async () => {
    vi.mocked(copilotApi.fetchPendingQuestions).mockResolvedValue([
      { question_id: 'broken', session_id: 's-1', questions: [{ not: 'a question' }], created_at: '' },
    ])

    await useCopilot.getState().loadPendingQuestions()

    expect(useCopilot.getState().pendingQuestions).toEqual([])
  })

  it('关闭卡片时连同草稿一起清掉（不残留脏草稿）', () => {
    useCopilot.getState().enqueueQuestion(question())
    useCopilot.getState().setQuestionDraft('qq-1', 'q1', { selections: ['甲合同'], text: '', comment: '' })

    useCopilot.getState().dismissQuestion('qq-1')

    expect(useCopilot.getState().pendingQuestions).toEqual([])
    expect(useCopilot.getState().questionDrafts).toEqual({})
  })

  it('切会话清空提问卡与草稿（跨会话泄漏回归用例）', async () => {
    vi.mocked(copilotApi.fetchHistory).mockResolvedValue([])
    useCopilot.getState().enqueueQuestion(question())
    useCopilot.getState().setQuestionDraft('qq-1', 'q1', { selections: ['甲合同'], text: '', comment: '' })

    await useCopilot.getState().switchSession('s-2')

    expect(useCopilot.getState().pendingQuestions).toEqual([])
    expect(useCopilot.getState().questionDrafts).toEqual({})
  })
})
