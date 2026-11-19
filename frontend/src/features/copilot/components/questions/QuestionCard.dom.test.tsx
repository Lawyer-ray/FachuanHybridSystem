// @vitest-environment jsdom
/**
 * QuestionCard 测试（jsdom）。
 *
 * 模型反问卡片的不变量：
 * - 一题一屏（1/N）+ 上一题/下一题保草稿
 * - 单选点击即选中；再点取消；多选累加
 * - 「提交」「跳过」都走 submitQuestion（未答=跳过由 store 判定）
 * - 已提交态隐藏动作按钮并回显服务端 note（含「本轮已继续」）
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const storeMock = vi.hoisted(() => ({
  questionDrafts: {} as Record<string, { selections: string[]; text: string; comment: string }>,
  setQuestionDraft: vi.fn(),
  submitQuestion: vi.fn(async () => {}),
  dismissQuestion: vi.fn(),
}))

vi.mock('../../store', () => ({
  useCopilot: (sel: (s: typeof storeMock) => unknown) => sel(storeMock),
}))
vi.mock('../../store/question', () => ({
  draftKey: (questionId: string, itemId: string) => `${questionId}:${itemId}`,
}))

import { QuestionCard } from './QuestionCard'
import type { PendingQuestion } from '../../types'

function card(over: Partial<PendingQuestion> = {}): PendingQuestion {
  return {
    questionId: 'qq-1',
    sessionId: 's-1',
    timeoutSeconds: 180,
    receivedAt: Date.now(),
    questions: [
      {
        id: 'q1',
        question: '以哪份合同为准？',
        context: '第三条：以签订地法院管辖。',
        options: [{ label: '甲合同', description: '2024 年签' }],
        allowFreeform: true,
        allowMultiple: false,
        allowComment: false,
      },
      {
        id: 'q2',
        question: '需要补哪些条款？',
        context: '',
        options: [
          { label: '违约责任', description: '' },
          { label: '争议解决', description: '' },
        ],
        allowFreeform: false,
        allowMultiple: true,
        allowComment: false,
      },
    ],
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  storeMock.questionDrafts = {}
})

describe('QuestionCard', () => {
  it('渲染题面、上下文与选项，并显示 1/N 进度', () => {
    render(<QuestionCard question={card()} />)
    expect(screen.getByText('以哪份合同为准？')).toBeTruthy()
    expect(screen.getByText('第三条：以签订地法院管辖。')).toBeTruthy()
    expect(screen.getByText('甲合同')).toBeTruthy()
    expect(screen.getByText('1 / 2')).toBeTruthy()
  })

  it('单选点击后写入草稿（toggleSelection 结果），并清空自由文本', () => {
    storeMock.questionDrafts = { 'qq-1:q1': { selections: [], text: '我要自己写', comment: '' } }
    render(<QuestionCard question={card()} />)
    fireEvent.click(screen.getByText('甲合同'))
    expect(storeMock.setQuestionDraft).toHaveBeenCalledWith('qq-1', 'q1', {
      selections: ['甲合同'],
      text: '',
      comment: '',
    })
  })

  it('多选可累加（第二题勾两个）', () => {
    storeMock.questionDrafts = { 'qq-1:q2': { selections: ['违约责任'], text: '', comment: '' } }
    render(<QuestionCard question={card()} />)
    fireEvent.click(screen.getByText('下一题'))
    fireEvent.click(screen.getByText('争议解决'))
    expect(storeMock.setQuestionDraft).toHaveBeenCalledWith('qq-1', 'q2', {
      selections: ['违约责任', '争议解决'],
      text: '',
      comment: '',
    })
  })

  it('翻页不丢草稿：第二题已有答案时回显勾选态', () => {
    storeMock.questionDrafts = { 'qq-1:q2': { selections: ['违约责任'], text: '', comment: '' } }
    render(<QuestionCard question={card()} />)
    fireEvent.click(screen.getByText('下一题'))
    expect(screen.getByRole('checkbox', { name: /违约责任/ }).getAttribute('aria-checked')).toBe('true')
    expect(screen.getByText('2 / 2')).toBeTruthy()
  })

  it('提交按钮走 submitQuestion（有题未答也允许提交，由 store 视为跳过）', () => {
    render(<QuestionCard question={card()} />)
    fireEvent.click(screen.getByText('提交'))
    expect(storeMock.submitQuestion).toHaveBeenCalledWith('qq-1')
  })

  it('跳过按钮同样走 submitQuestion', () => {
    render(<QuestionCard question={card()} />)
    fireEvent.click(screen.getByText('跳过'))
    expect(storeMock.submitQuestion).toHaveBeenCalledWith('qq-1')
  })

  it('已提交态隐藏动作按钮并回显服务端 note', () => {
    render(
      <QuestionCard
        question={card({ submitted: 'answered', continued: true, note: '回答已记录，但本轮对话已按超时继续' })}
      />,
    )
    expect(screen.getByText('回答已记录，但本轮对话已按超时继续')).toBeTruthy()
    expect(screen.queryByText('提交')).toBeNull()
    expect(screen.queryByText('跳过')).toBeNull()
  })

  it('关闭按钮调 dismissQuestion', () => {
    render(<QuestionCard question={card()} />)
    fireEvent.click(screen.getByTitle(/关闭/))
    expect(storeMock.dismissQuestion).toHaveBeenCalledWith('qq-1')
  })
})
