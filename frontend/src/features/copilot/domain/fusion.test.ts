/**
 * 评审契约 → 视图的纯映射（node 环境）。
 *
 * 这些用例锁的都是「不报错但会说错话」的口径：
 * - `criteria_met === null` 是**判不了**，不是 false（折算成不通过就是冤枉回答）；
 * - `score === null` 是**无有效判定**，不是 0 分；
 * - `tie === true` 时没有任何簇被突出（不做推荐排序，是契约语义）；
 * - 未知 `unscored_reason` 不崩、原样降级。
 */

import { describe, expect, it } from 'vitest'

import type { CriteriaVerdict, EquivalenceCluster, LaneReview, Review, Synthesis } from '../adjudication-types'
import {
  conflictPairsOf,
  droppedReasonLabel,
  reviewTurnOf,
  toClusterViews,
  toReviewView,
  toSynthesisView,
  unscoredLabelOf,
} from './fusion'

const lane = (over: Partial<LaneReview> = {}): LaneReview => ({
  lane: 'pi',
  valid: 2,
  yes: 1,
  score: 0.5,
  one_line: '2 条已判，1 条通过',
  ...over,
})

const verdict = (over: Partial<CriteriaVerdict> = {}): CriteriaVerdict => ({
  rubric_id: 'r1',
  lane: 'pi',
  criteria_met: true,
  explanation: '',
  evidence_quote: '',
  judge_model: 'judge-a',
  attempts: 1,
  unscored_reason: '',
  ...over,
})

const review = (over: Partial<Review> = {}): Review => ({
  review_id: 'rv-1',
  session_id: 's-1',
  turn: 2,
  rubric_id: 'contract-basic',
  rubric_version: 'v1',
  stage: 'shadow',
  lanes: [],
  verdicts: [],
  headline: '',
  unverified: [],
  clusters: [],
  clusters_error: '',
  ...over,
})

const cluster = (over: Partial<EquivalenceCluster> = {}): EquivalenceCluster => ({
  member_ids: ['a1'],
  representative_id: 'a1',
  tie: false,
  ...over,
})

describe('toReviewView：snake_case → camelCase', () => {
  it('字段逐个改名，值不改写', () => {
    const view = toReviewView(
      review({
        headline: 'pi 栏多数通过；dsh 栏多数未通过',
        lanes: [lane({ lane: 'dsh', valid: 3, yes: 2, score: 2 / 3, one_line: '3 条已判，2 条通过' })],
        verdicts: [verdict({ rubric_id: 'r7', lane: 'dsh', criteria_met: false, evidence_quote: '原文' })],
      }),
    )
    expect(view.reviewId).toBe('rv-1')
    expect(view.stage).toBe('shadow')
    expect(view.headline).toBe('pi 栏多数通过；dsh 栏多数未通过')
    expect(view.lanes).toEqual([
      { lane: 'dsh', label: 'DeepSeek Harness', valid: 3, yes: 2, score: 2 / 3, oneLine: '3 条已判，2 条通过' },
    ])
    expect(view.verdicts[0]).toMatchObject({ rubricId: 'r7', lane: 'dsh', met: false, evidenceQuote: '原文' })
  })

  it('score=null 原样保留（无有效判定，不是 0 分）', () => {
    const view = toReviewView(review({ lanes: [lane({ valid: 0, yes: 0, score: null, one_line: '无有效判定（3 条判不了）' })] }))
    expect(view.lanes[0]!.score).toBeNull()
    // 0 会让视图显示「0%」，null 才会显示「无有效判定」
    expect(view.lanes[0]!.score).not.toBe(0)
  })

  it('criteria_met=null 映射成判不了（met 保持 null，带上原因），不是 false', () => {
    const view = toReviewView(
      review({
        verdicts: [verdict({ criteria_met: null, unscored_reason: 'timeout' })],
      }),
    )
    expect(view.verdicts[0]!.met).toBeNull()
    expect(view.verdicts[0]!.met).not.toBe(false)
    expect(view.verdicts[0]!.unscoredReason).toBe('judge 超时')
  })

  it('有判定时即使线上留了 unscored_reason 也不展示（只有判不了才有原因）', () => {
    const view = toReviewView(review({ verdicts: [verdict({ criteria_met: true, unscored_reason: 'timeout' })] }))
    expect(view.verdicts[0]!.unscoredReason).toBe('')
  })

  it('clusters 走 toClusterViews（成员/代表/emphasized 一并映射）', () => {
    const view = toReviewView(
      review({
        clusters: [
          cluster({ member_ids: ['pi', 'dsh'], representative_id: 'pi', tie: false }),
          cluster({ member_ids: ['openai-agents'], representative_id: 'openai-agents', tie: false }),
        ],
      }),
    )
    expect(view.clusters).toEqual([
      { memberIds: ['pi', 'dsh'], representativeId: 'pi', tie: false, emphasized: true },
      { memberIds: ['openai-agents'], representativeId: 'openai-agents', tie: false, emphasized: true },
    ])
  })

  it('tie=true 的簇进视图后不被突出、代表清空（不自己找「第一条」）', () => {
    const view = toReviewView(
      review({
        clusters: [
          cluster({ member_ids: ['pi'], representative_id: 'pi', tie: true }),
          cluster({ member_ids: ['dsh'], representative_id: 'dsh', tie: true }),
        ],
      }),
    )
    expect(view.clusters.every((item) => item.emphasized === false)).toBe(true)
    expect(view.clusters.every((item) => item.representativeId === '')).toBe(true)
  })

  it('clusters_error 原样透传（空串 = 成功或未跑，非空 = 成团失败的原因）', () => {
    expect(toReviewView(review()).clustersError).toBe('')
    expect(toReviewView(review({ clusters_error: '判等超时' })).clustersError).toBe('判等超时')
  })
})

describe('unscoredLabelOf：未知原因降级', () => {
  it('闭集内的原因给人读文案', () => {
    expect(unscoredLabelOf('parse_failed')).toBe('判定解析失败')
    expect(unscoredLabelOf('judge_error')).toBe('judge 调用失败')
  })

  it('后端将来新增原因：原样显示，不崩也不吞', () => {
    expect(unscoredLabelOf('rate_limited')).toBe('rate_limited')
    expect(unscoredLabelOf('')).toBe('')
  })
})

describe('conflictPairsOf：同一条 rubric 的相反判定', () => {
  it('一方成立一方不成立 → 一个分歧点，两侧各带原文', () => {
    const pairs = conflictPairsOf([
      verdict({ rubric_id: 'r2', lane: 'pi', criteria_met: true, evidence_quote: '甲方应于 6 个月内付款' }),
      verdict({ rubric_id: 'r2', lane: 'dsh', criteria_met: false, evidence_quote: '未见付款期限约定' }),
    ])
    expect(pairs).toHaveLength(1)
    expect(pairs[0]!.rubricId).toBe('r2')
    expect(pairs[0]!.sides.map((side) => [side.lane, side.met, side.evidenceQuote])).toEqual([
      ['pi', true, '甲方应于 6 个月内付款'],
      ['dsh', false, '未见付款期限约定'],
    ])
  })

  it('意见一致不算分歧', () => {
    const pairs = conflictPairsOf([
      verdict({ rubric_id: 'r1', lane: 'pi', criteria_met: true }),
      verdict({ rubric_id: 'r1', lane: 'dsh', criteria_met: true }),
    ])
    expect(pairs).toEqual([])
  })

  it('判不了不算立场：null 与 true 并存不构成分歧', () => {
    const pairs = conflictPairsOf([
      verdict({ rubric_id: 'r1', lane: 'pi', criteria_met: true }),
      verdict({ rubric_id: 'r1', lane: 'dsh', criteria_met: null, unscored_reason: 'timeout' }),
    ])
    expect(pairs).toEqual([])
  })

  it('不同 rubric 各算各的，出现顺序按 verdict 到达顺序', () => {
    const pairs = conflictPairsOf([
      verdict({ rubric_id: 'r9', lane: 'pi', criteria_met: false }),
      verdict({ rubric_id: 'r3', lane: 'pi', criteria_met: true }),
      verdict({ rubric_id: 'r9', lane: 'dsh', criteria_met: true }),
      verdict({ rubric_id: 'r3', lane: 'dsh', criteria_met: false }),
    ])
    expect(pairs.map((pair) => pair.rubricId)).toEqual(['r9', 'r3'])
  })
})

describe('toClusterViews：tie 时不许突出任何簇', () => {
  it('tie=true：所有簇都不突出、代表清空，且不做推荐排序', () => {
    const views = toClusterViews([
      cluster({ member_ids: ['a2'], representative_id: 'a2', tie: true }),
      cluster({ member_ids: ['a1'], representative_id: 'a1', tie: true }),
    ])
    // 顺序原样：即使第二簇"更早"，也不许重排成推荐顺序
    expect(views.map((view) => view.memberIds[0])).toEqual(['a2', 'a1'])
    expect(views.every((view) => view.emphasized === false)).toBe(true)
    expect(views.every((view) => view.representativeId === '')).toBe(true)
  })

  it('非 tie：代表簇可突出，顺序仍按输入（不按大小排序）', () => {
    const views = toClusterViews([
      cluster({ member_ids: ['a1'], representative_id: 'a1', tie: false }),
      cluster({ member_ids: ['a2', 'a3'], representative_id: 'a2', tie: false }),
    ])
    expect(views.map((view) => view.memberIds.length)).toEqual([1, 2])
    expect(views.every((view) => view.emphasized === true)).toBe(true)
    expect(views[1]!.representativeId).toBe('a2')
  })
})

describe('droppedReasonLabel：丢弃原因的三种人读文案', () => {
  it('封闭集内给人读原因（不是「没参与」这种模糊说法）', () => {
    expect(droppedReasonLabel('empty')).toBe('本轮无正文')
    expect(droppedReasonLabel('failed')).toBe('本轮失败')
    expect(droppedReasonLabel('too_long')).toBe('超长被截')
  })

  it('后端将来新增原因：原样显示，不崩也不吞', () => {
    expect(droppedReasonLabel('rate_limited')).toBe('rate_limited')
  })
})

describe('toSynthesisView：综合结论 snake_case → camelCase', () => {
  const synthesis = (over: Partial<Synthesis> = {}): Synthesis => ({
    synthesis_id: 'sy-1',
    session_id: 's-1',
    turn: 2,
    text: '## 结论\n\n甲方可主张解除',
    model: 'kimi-2.6',
    lanes_used: ['pi', 'dsh'],
    dropped: [{ lane: 'openai-agents', reason: 'empty' }],
    citations: [{ lane: 'pi', quote: '《民法典》第五百八十四条' }],
    unverified: ['pi 引《X 办法》第 7 条，本轮无核验命中'],
    tokens: { prompt: 2100, completion: 640, total: 2740 },
    ...over,
  })

  it('字段逐个改名，栏名带上人读标签，顺序不改写', () => {
    const view = toSynthesisView(synthesis())
    expect(view.synthesisId).toBe('sy-1')
    expect(view.text).toContain('甲方可主张解除')
    expect(view.model).toBe('kimi-2.6')
    expect(view.lanesUsed).toEqual([
      { lane: 'pi', label: 'Pi' },
      { lane: 'dsh', label: 'DeepSeek Harness' },
    ])
    expect(view.dropped).toEqual([{ lane: 'openai-agents', label: 'openai-agents', reason: '本轮无正文' }])
    expect(view.citations).toEqual([{ lane: 'pi', label: 'Pi', quote: '《民法典》第五百八十四条' }])
    expect(view.unverified).toEqual(['pi 引《X 办法》第 7 条，本轮无核验命中'])
    expect(view.tokens).toEqual({ prompt: 2100, completion: 640, total: 2740 })
  })

  it('dropped 的三个原因都翻成人话（空 / 失败 / 超长）', () => {
    const view = toSynthesisView(
      synthesis({
        dropped: [
          { lane: 'pi', reason: 'empty' },
          { lane: 'dsh', reason: 'failed' },
          { lane: 'openai-agents', reason: 'too_long' },
        ],
      }),
    )
    expect(view.dropped.map((item) => item.reason)).toEqual(['本轮无正文', '本轮失败', '超长被截'])
  })
})

describe('reviewTurnOf：评审卡挂在哪一轮', () => {
  const messages = [
    { id: 'u1', role: 'user' },
    { id: 'a1', role: 'assistant' },
    { id: 'u2', role: 'user' },
    { id: 't2', role: 'tool' },
    { id: 'a2', role: 'assistant' },
  ]

  it('后端口径：turn = 第几条 user 消息（1 起）', () => {
    expect(reviewTurnOf(messages, 'a1', true)).toBe(1)
    expect(reviewTurnOf(messages, 'a2', true)).toBe(2)
  })

  it('user 消息自己开启新一轮', () => {
    expect(reviewTurnOf(messages, 'u2', true)).toBe(2)
  })

  it('窗口不完整（>200 条老会话的最新一页）时不猜：返回 null', () => {
    expect(reviewTurnOf(messages, 'a2', false)).toBeNull()
  })

  it('消息不在当前转录里（还没回填）时返回 null', () => {
    expect(reviewTurnOf(messages, 'a9', true)).toBeNull()
  })
})
