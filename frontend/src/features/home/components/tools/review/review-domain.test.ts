/**
 * 块级可信度复核纯逻辑单测（node 环境）。
 *
 * 重点全部压在一条语义边界上：`confidence === null`（未评估）≠ `0`（评估为错）。
 * 任何把 null 当 falsy / 当 0 的写法都会让这条边界塌掉，所以这里逐点钉死。
 */
import { describe, expect, it } from 'vitest'

import type { ParseBlock } from './review-domain'
import {
  REVIEW_THRESHOLD,
  canAttachConfidence,
  filterBlocks,
  formatConfidence,
  groupByPage,
  isBodyBlock,
  needsReview,
  reviewHeadline,
  reviewStats,
  scoreState,
} from './review-domain'

function block(over: Partial<ParseBlock> = {}): ParseBlock {
  return { type: 'text', text: 'x', ...over } as ParseBlock
}

describe('scoreState（null 安全是全部意义）', () => {
  it('null 是未评估，不是 0 分', () => {
    expect(scoreState(block({ confidence: null }))).toBe('unscored')
  })

  it('缺字段也是未评估', () => {
    expect(scoreState(block())).toBe('unscored')
  })

  it('0 分是 risky，不能被当成 falsy 归到未评估', () => {
    expect(scoreState(block({ confidence: 0 }))).toBe('risky')
  })

  it('阈值边界：等于阈值算 confident，低于算 risky', () => {
    expect(scoreState(block({ confidence: REVIEW_THRESHOLD }))).toBe('confident')
    expect(scoreState(block({ confidence: REVIEW_THRESHOLD - 0.01 }))).toBe('risky')
  })

  it('1 分是 confident', () => {
    expect(scoreState(block({ confidence: 1 }))).toBe('confident')
  })
})

describe('needsReview', () => {
  it('未评估不进复核清单（否则引擎一不支持打分整页全红，用户直接无视）', () => {
    expect(needsReview(block({ confidence: null }))).toBe(false)
  })

  it('低分进清单', () => {
    expect(needsReview(block({ confidence: 0.3 }))).toBe(true)
  })

  it('后端显式标记则进清单（即使没有分数）', () => {
    expect(needsReview(block({ confidence: null, needs_review: true }))).toBe(true)
  })

  it('高分且未标记不进清单', () => {
    expect(needsReview(block({ confidence: 0.99 }))).toBe(false)
  })
})

describe('isBodyBlock', () => {
  it('页眉页脚页码不算正文', () => {
    expect(isBodyBlock(block({ type: 'header' }))).toBe(false)
    expect(isBodyBlock(block({ type: 'footer' }))).toBe(false)
  })

  it('正文/标题/表格/公式都算正文', () => {
    for (const t of ['text', 'title', 'table', 'formula'] as const) {
      expect(isBodyBlock(block({ type: t }))).toBe(true)
    }
  })
})

describe('groupByPage', () => {
  it('按页分组并保持页序与页内顺序', () => {
    const groups = groupByPage([
      block({ page_no: 1, text: 'a' }),
      block({ page_no: 1, text: 'b' }),
      block({ page_no: 2, text: 'c' }),
    ])
    expect(groups).toHaveLength(2)
    expect(groups[0]?.pageNo).toBe(1)
    expect(groups[0]?.blocks.map((b) => b.text)).toEqual(['a', 'b'])
    expect(groups[1]?.pageNo).toBe(2)
  })

  it('无页码归到 pageNo=null 组', () => {
    const groups = groupByPage([block({ page_no: null }), block({ page_no: 3 })])
    expect(groups.map((g) => g.pageNo)).toEqual([null, 3])
  })

  it('空输入返回空数组', () => {
    expect(groupByPage([])).toEqual([])
  })
})

describe('reviewStats', () => {
  it('分别统计 flagged / risky / unscored / confident', () => {
    const stats = reviewStats([
      block({ confidence: null }),
      block({ confidence: 0.2, page_no: 1 }),
      block({ confidence: 0.95, page_no: 1 }),
      block({ type: 'footer', confidence: 0.1 }), // 页脚：flagged 但不算 body
    ])
    expect(stats.total).toBe(4)
    expect(stats.body).toBe(3)
    expect(stats.unscored).toBe(1)
    expect(stats.risky).toBe(2)
    expect(stats.confident).toBe(1)
    expect(stats.flagged).toBe(2)
  })

  it('空列表全零', () => {
    expect(reviewStats([])).toEqual({ total: 0, body: 0, flagged: 0, risky: 0, unscored: 0, confident: 0 })
  })
})

describe('filterBlocks', () => {
  const list = [
    block({ confidence: null, text: 'unscored' }),
    block({ confidence: 0.3, text: 'risky' }),
    block({ confidence: 0.9, text: 'confident' }),
  ]

  it('all 不过滤', () => {
    expect(filterBlocks(list, 'all')).toHaveLength(3)
  })

  it('flagged 只留需复核', () => {
    expect(filterBlocks(list, 'flagged').map((b) => b.text)).toEqual(['risky'])
  })

  it('scored 只留有分数的（null 排除）', () => {
    expect(filterBlocks(list, 'scored').map((b) => b.text)).toEqual(['risky', 'confident'])
  })

  it('unscored 只留未评估的', () => {
    expect(filterBlocks(list, 'unscored').map((b) => b.text)).toEqual(['unscored'])
  })
})

describe('reviewHeadline（措辞不能替沉默背书）', () => {
  it('没有块', () => {
    expect(reviewHeadline(reviewStats([]))).toBe('本次解析没有块级结构')
  })

  it('有需复核块时优先报数', () => {
    expect(reviewHeadline(reviewStats([block({ confidence: 0.1 })]))).toContain('待复核')
  })

  it('全部未评估时说明「未评估」，不能说「全部可信」', () => {
    const text = reviewHeadline(reviewStats([block({ confidence: null }), block({ confidence: null })]))
    expect(text).toContain('未评估')
    expect(text).not.toContain('阈值以上')
  })

  it('全部达标才说阈值以上', () => {
    expect(reviewHeadline(reviewStats([block({ confidence: 0.99 })]))).toContain('阈值以上')
  })
})

describe('formatConfidence', () => {
  it('null 显示破折号而不是 0.00', () => {
    expect(formatConfidence(null)).toBe('—')
    expect(formatConfidence(undefined)).toBe('—')
  })

  it('0 显示 0.00（与未评估明确区分）', () => {
    expect(formatConfidence(0)).toBe('0.00')
  })

  it('两位小数', () => {
    expect(formatConfidence(0.856)).toBe('0.86')
  })
})

describe('canAttachConfidence（只读后端声明，不猜）', () => {
  it('有块且有坐标才算能外挂', () => {
    expect(canAttachConfidence({ has_blocks: true, has_bbox: true } as never)).toBe(true)
  })

  it('缺坐标不能外挂', () => {
    expect(canAttachConfidence({ has_blocks: true, has_bbox: false } as never)).toBe(false)
  })

  it('无能力位时不谎称可以', () => {
    expect(canAttachConfidence(null)).toBe(false)
    expect(canAttachConfidence(undefined)).toBe(false)
  })
})
