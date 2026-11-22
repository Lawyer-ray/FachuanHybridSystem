// @vitest-environment jsdom
/**
 * 多答裁决卡（jsdom）：汇总卡 / 分歧两侧 / 证据展开 / 采纳条 / 无数据不渲染。
 *
 * 锁的都是一旦错了"看起来正常但会说错话"的地方：
 * - `score === null` 显示「无有效判定」，绝不能显示 0%；
 * - judge 判不了的条目带原因（超时/解析失败的可信度完全不同）；
 * - 分歧点把两侧 judge 引用的原句并排显示；
 * - 采纳回显把「合并」与「采纳某一栏」分开，且 404 = 没记录而不是错误；
 * - 没有评审数据时整块不渲染（不显示空卡）。
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiSpies = vi.hoisted(() => ({
  fetchReview: vi.fn(),
  adoptReview: vi.fn(),
  fetchReviewAdoption: vi.fn(),
  fetchReviewOptions: vi.fn(),
  fetchSynthesis: vi.fn(),
  runReview: vi.fn(),
  runSynthesis: vi.fn(),
}))
vi.mock('../../api', async () => {
  const actual = await vi.importActual<typeof import('../../api')>('../../api')
  return { ...actual, ...apiSpies }
})

import type { CriteriaVerdict, LaneReview, Review } from '../../adjudication-types'
import type { ReviewAdoptionWire } from '../../domain/adoption'
import { toReviewView } from '../../domain/fusion'
import type { ChatMessage } from '../../types'
import { MultiAnswers } from '../MultiAnswers'
import { ReviewSummaryCard } from './ReviewSummaryCard'
import { agentLabel } from '../../domain/dual'

const lane = (over: Partial<LaneReview> = {}): LaneReview => ({
  lane: 'pi',
  valid: 2,
  yes: 1,
  score: 0.5,
  one_line: '2 条已判，1 条通过',
  ...over,
})

const verdict = (over: Partial<CriteriaVerdict> = {}): CriteriaVerdict => ({
  rubric_id: 'r2',
  lane: 'pi',
  criteria_met: true,
  explanation: '',
  evidence_quote: '',
  judge_model: 'judge-a',
  attempts: 1,
  unscored_reason: '',
  ...over,
})

const reviewWire = (over: Partial<Review> = {}): Review => ({
  review_id: 'rv-1',
  session_id: 's-1',
  turn: 2,
  rubric_id: 'contract-basic',
  rubric_version: 'v1',
  stage: 'shadow',
  lanes: [lane(), lane({ lane: 'dsh', valid: 2, yes: 1, score: 0.5 })],
  verdicts: [verdict()],
  headline: 'pi 栏多数通过；dsh 栏多数通过',
  unverified: [],
  clusters: [],
  clusters_error: '',
  ...over,
})

const adoptionWire = (over: Partial<ReviewAdoptionWire> = {}): ReviewAdoptionWire => ({
  review_id: 'rv-1',
  lane: 'pi',
  merged: false,
  note: '',
  adopted_at: '2026-11-21T00:30:00Z',
  ...over,
})

beforeEach(() => {
  vi.clearAllMocks()
  apiSpies.fetchReviewAdoption.mockResolvedValue({ adoption: null })
  apiSpies.fetchReviewOptions.mockResolvedValue({
    rubric_ids: ['contract_answer_v1'],
    judge_models: ['judge-a'],
    max_lanes: 4,
  })
  // 404 = 该轮还没跑过综合结论（正常态）
  apiSpies.fetchSynthesis.mockRejectedValue(new Error('404'))
})

describe('ReviewSummaryCard：汇总与证据', () => {
  it('headline + 每栏 one_line；score=null 显示无有效判定（不是 0%）', () => {
    render(
      <ReviewSummaryCard
        review={toReviewView(
          reviewWire({
            lanes: [lane(), lane({ lane: 'dsh', valid: 0, yes: 0, score: null, one_line: '无有效判定（3 条判不了）' })],
          }),
        )}
      />,
    )
    expect(screen.getByTestId('review-headline').textContent).toBe('pi 栏多数通过；dsh 栏多数通过')
    expect(screen.getByText('2 条已判，1 条通过')).toBeTruthy()
    expect(screen.getByTestId('lane-score-pi').textContent).toBe('50%')
    expect(screen.getByTestId('lane-score-dsh').textContent).toBe('无有效判定')
    expect(screen.queryByText('0%')).toBeNull()
  })

  it('点分数展开 rubric 条目 + judge 引用的原文片段', () => {
    render(
      <ReviewSummaryCard
        review={toReviewView(
          reviewWire({
            verdicts: [
              verdict({ rubric_id: 'r2', explanation: '条款已约定分期', evidence_quote: '甲方应于 6 个月内付款' }),
            ],
          }),
        )}
      />,
    )
    // 展开前不渲染证据
    expect(screen.queryByTestId('evidence-item')).toBeNull()
    fireEvent.click(screen.getByTestId('lane-score-pi'))
    expect(screen.getByTestId('evidence-item')).toBeTruthy()
    expect(screen.getByText('r2')).toBeTruthy()
    expect(screen.getByText(/条款已约定分期/)).toBeTruthy()
    expect(screen.getByTestId('evidence-quote').textContent).toContain('甲方应于 6 个月内付款')
  })

  it('judge 判不了的条目显示原因（判不了 ≠ 不通过）', () => {
    render(
      <ReviewSummaryCard
        review={toReviewView(
          reviewWire({ verdicts: [verdict({ criteria_met: null, unscored_reason: 'timeout' })] }),
        )}
      />,
    )
    fireEvent.click(screen.getByTestId('lane-score-pi'))
    expect(screen.getByText('判不了 · judge 超时')).toBeTruthy()
    expect(screen.queryByText('不通过')).toBeNull()
  })

  it('分歧点并排显示两侧原句', () => {
    render(
      <ReviewSummaryCard
        review={toReviewView(
          reviewWire({
            verdicts: [
              verdict({ rubric_id: 'r7', lane: 'pi', criteria_met: true, evidence_quote: '甲方应于 6 个月内付款' }),
              verdict({ rubric_id: 'r7', lane: 'dsh', criteria_met: false, evidence_quote: '未见付款期限约定' }),
            ],
          }),
        )}
      />,
    )
    const conflicts = screen.getByTestId('review-conflicts')
    expect(conflicts.textContent).toContain('甲方应于 6 个月内付款')
    expect(conflicts.textContent).toContain('未见付款期限约定')
    expect(screen.getByTestId('conflict-r7')).toBeTruthy()
  })

  it('没有分歧时不渲染分歧区', () => {
    render(<ReviewSummaryCard review={toReviewView(reviewWire())} />)
    expect(screen.queryByTestId('review-conflicts')).toBeNull()
  })
})

describe('ReviewSummaryCard：共识 / 分歧（成团）', () => {
  it('多于一栏的簇 = 共识，单栏 = 单独立场；非 tie 时突出代表', () => {
    render(
      <ReviewSummaryCard
        review={toReviewView(
          reviewWire({
            clusters: [
              { member_ids: ['pi', 'dsh'], representative_id: 'pi', tie: false },
              { member_ids: ['openai-agents'], representative_id: 'openai-agents', tie: false },
            ],
          }),
        )}
      />,
    )
    const list = screen.getByTestId('review-clusters')
    expect(list.textContent).toContain('共识：Pi、DeepSeek Harness')
    expect(list.textContent).toContain(`单独立场：${agentLabel('openai-agents')}`)
    expect(screen.getByTestId('cluster-0').getAttribute('data-emphasized')).toBe('true')
    expect(screen.getByTestId('cluster-0').textContent).toContain('代表 Pi')
  })

  it('clustersError 非空：显示「未成团：原因」，绝不显示成「三份全异」', () => {
    render(<ReviewSummaryCard review={toReviewView(reviewWire({ clusters_error: '判等超时' }))} />)
    expect(screen.getByTestId('clusters-error').textContent).toBe('未成团：判等超时')
    expect(screen.queryByTestId('cluster-0')).toBeNull()
    // 失败不是一个结论：既不能说「三份全异」，也不能冒出任何立场组
    expect(screen.getByTestId('review-clusters').textContent).not.toContain('全异')
    expect(screen.getByTestId('review-clusters').textContent).not.toContain('共识：')
    expect(screen.getByTestId('review-clusters').textContent).not.toContain('单独立场')
  })

  it('tie=true：所有簇都不加高亮，也不提示代表', () => {
    render(
      <ReviewSummaryCard
        review={toReviewView(
          reviewWire({
            clusters: [
              { member_ids: ['pi'], representative_id: 'pi', tie: true },
              { member_ids: ['dsh'], representative_id: 'dsh', tie: true },
            ],
          }),
        )}
      />,
    )
    expect(screen.queryAllByTestId(/^cluster-\d+$/).every((item) => item.getAttribute('data-emphasized') === null)).toBe(true)
    expect(screen.getByTestId('clusters-tie').textContent).toContain('没有可判定的代表')
    expect(screen.getByTestId('review-clusters').textContent).not.toContain('代表 Pi')
  })

  it('没有成团结果（空簇且无错误）= 没跑成团：整块不渲染', () => {
    render(<ReviewSummaryCard review={toReviewView(reviewWire())} />)
    expect(screen.queryByTestId('review-clusters')).toBeNull()
    expect(screen.queryByTestId('clusters-error')).toBeNull()
  })
})

describe('AdoptBar：采纳 / 合并 / 回显', () => {
  it('采纳某一栏：POST 带 lane/merged/note，成功后本地回显（不重取评审）', async () => {
    apiSpies.adoptReview.mockResolvedValue(adoptionWire({ lane: 'pi', merged: false, note: '最贴题' }))
    render(<ReviewSummaryCard review={toReviewView(reviewWire())} />)

    fireEvent.change(screen.getByLabelText('采纳理由'), { target: { value: '最贴题' } })
    fireEvent.click(screen.getByRole('button', { name: '采纳 Pi' }))

    await waitFor(() =>
      expect(apiSpies.adoptReview).toHaveBeenCalledWith('rv-1', { lane: 'pi', merged: false, note: '最贴题' }),
    )
    expect((await screen.findByTestId('adopt-state')).textContent).toContain('已采纳 Pi')
    // 判定快照不因采纳而变：不整页重取 review
    expect(apiSpies.fetchReview).not.toHaveBeenCalled()
  })

  it('标为合并：POST lane=null + merged=true，回显「已标为合并采纳」而不是空栏', async () => {
    apiSpies.adoptReview.mockResolvedValue(adoptionWire({ lane: null, merged: true, note: '先合并两版' }))
    render(<ReviewSummaryCard review={toReviewView(reviewWire())} />)

    fireEvent.change(screen.getByLabelText('采纳理由'), { target: { value: '先合并两版' } })
    fireEvent.click(screen.getByRole('button', { name: '标为合并' }))

    await waitFor(() =>
      expect(apiSpies.adoptReview).toHaveBeenCalledWith('rv-1', { lane: null, merged: true, note: '先合并两版' }),
    )
    const state = (await screen.findByTestId('adopt-state')).textContent ?? ''
    expect(state).toContain('已标为合并采纳')
    expect(state).toContain('理由：先合并两版')
    expect(state).not.toContain('null')
  })

  it('挂载时 GET adoption 回显已有采纳（刷新可回放）', async () => {
    apiSpies.fetchReviewAdoption.mockResolvedValue({ adoption: adoptionWire({ lane: null, merged: true, note: '两版一致' }) })
    render(<ReviewSummaryCard review={toReviewView(reviewWire())} />)
    const state = await screen.findByTestId('adopt-state')
    expect(state.textContent).toContain('已标为合并采纳')
    expect(state.textContent).toContain('理由：两版一致')
  })

  it('GET adoption 404 = 还没有记录：静默、不弹错、不阻塞渲染', async () => {
    apiSpies.fetchReviewAdoption.mockRejectedValue(new Error('404'))
    render(<ReviewSummaryCard review={toReviewView(reviewWire())} />)
    await waitFor(() => expect(apiSpies.fetchReviewAdoption).toHaveBeenCalledWith('rv-1'))
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByTestId('adopt-state')).toBeNull()
    expect(screen.getByTestId('review-summary')).toBeTruthy()
  })

  it('POST 失败时给出人话错误，且不伪造采纳态', async () => {
    apiSpies.adoptReview.mockRejectedValue(new Error('网络抖动'))
    render(<ReviewSummaryCard review={toReviewView(reviewWire())} />)
    fireEvent.click(screen.getByRole('button', { name: '采纳 Pi' }))
    expect((await screen.findByRole('alert')).textContent).toContain('网络抖动')
    expect(screen.queryByTestId('adopt-state')).toBeNull()
  })
})


/** 综合结论的 wire 形状（`toSynthesisView` 只读这几个字段）。 */
function synthesisWire() {
  return {
    synthesis_id: 'syn-1',
    session_id: 's-1',
    turn: 2,
    text: '综合稿[来源：pi]',
    model: 'kimi-2.6',
    lanes_used: ['pi', 'dsh'],
    dropped: [],
    citations: [],
    unverified: [],
    tokens: {},
  }
}

describe('MultiAnswers：无评审数据整块不渲染', () => {
  const answers: ChatMessage[] = [
    { id: 'a1', role: 'assistant', content: '主答', agentKind: 'pi' },
    { id: 'a2', role: 'assistant', content: '次答', agentKind: 'dsh' },
  ]

  it('该轮没有评审（404）→ 不渲染空卡；只给「生成综合结论」按钮且不自动跑', async () => {
    apiSpies.fetchReview.mockRejectedValue(new Error('404'))
    render(
      <MultiAnswers
        answers={answers}
        renderAnswer={() => <div />}
        reviewTarget={{ sessionId: 's-1', turn: 2 }}
      />,
    )
    await waitFor(() => expect(apiSpies.fetchReview).toHaveBeenCalledWith('s-1', 2))
    expect(screen.queryByTestId('review-summary')).toBeNull()
    // 只有一个入口：评审并进了综合按钮（打分是其中一步，不再需要先点一次）
    expect(screen.queryByRole('button', { name: '评审' })).toBeNull()
    expect(await screen.findByRole('button', { name: '生成综合结论' })).toBeTruthy()
    // 花了才跑：还没点，绝不能已经发过 POST
    expect(apiSpies.runReview).not.toHaveBeenCalled()
    expect(apiSpies.runSynthesis).not.toHaveBeenCalled()
  })

  it('点「生成综合结论」：默认带 review=true（先评审后综合），不为评审单独发请求', async () => {
    apiSpies.fetchReview.mockRejectedValue(new Error('404'))
    apiSpies.runSynthesis.mockResolvedValue(synthesisWire())
    render(
      <MultiAnswers
        answers={answers}
        renderAnswer={() => <div />}
        reviewTarget={{ sessionId: 's-1', turn: 2 }}
      />,
    )
    fireEvent.click(await screen.findByRole('button', { name: '生成综合结论' }))
    await waitFor(() =>
      expect(apiSpies.runSynthesis).toHaveBeenCalledWith('s-1', {
        turn: 2,
        agents: ['pi', 'dsh'],
        model: '',
        kind: 'pi',
        review: true,
      }),
    )
    // 评审不再单独 POST：它由后端在综合请求里一并跑
    expect(apiSpies.runReview).not.toHaveBeenCalled()
  })

  it('取消勾选「先评审」→ review=false', async () => {
    apiSpies.fetchReview.mockRejectedValue(new Error('404'))
    apiSpies.runSynthesis.mockResolvedValue(synthesisWire())
    render(
      <MultiAnswers
        answers={answers}
        renderAnswer={() => <div />}
        reviewTarget={{ sessionId: 's-1', turn: 2 }}
      />,
    )
    const checkbox = (await screen.findByTestId('synthesis-with-review')) as HTMLInputElement
    expect(checkbox.checked).toBe(true)
    fireEvent.click(checkbox)
    fireEvent.click(screen.getByRole('button', { name: '生成综合结论' }))
    await waitFor(() => expect(apiSpies.runSynthesis).toHaveBeenCalledWith('s-1', expect.objectContaining({ review: false })))
  })

  it('平台没有可用评审模型 → 不禁用按钮，提示"本次会跳过评审直接综合"', async () => {
    apiSpies.fetchReview.mockRejectedValue(new Error('404'))
    apiSpies.fetchReviewOptions.mockResolvedValue({ rubric_ids: [], judge_models: [], max_lanes: 5 })
    render(
      <MultiAnswers
        answers={answers}
        renderAnswer={() => <div />}
        reviewTarget={{ sessionId: 's-1', turn: 2 }}
      />,
    )
    const button = (await screen.findByRole('button', { name: '生成综合结论' })) as HTMLButtonElement
    expect(button.disabled).toBe(false)
    expect((await screen.findByTestId('review-models-missing')).textContent).toContain('跳过评审')
  })

  it('有评审 → 挂出汇总卡；综合按钮始终在（不再依赖评审先跑完）', async () => {
    apiSpies.fetchReview.mockResolvedValue(reviewWire())
    render(
      <MultiAnswers
        answers={answers}
        renderAnswer={() => <div />}
        reviewTarget={{ sessionId: 's-1', turn: 2 }}
      />,
    )
    expect((await screen.findByTestId('review-summary')).textContent).toContain('pi 栏多数通过')
    expect(screen.getByTestId('multi-answers')).toBeTruthy()
    expect(await screen.findByRole('button', { name: '生成综合结论' })).toBeTruthy()
    expect(apiSpies.runSynthesis).not.toHaveBeenCalled()
  })
})
