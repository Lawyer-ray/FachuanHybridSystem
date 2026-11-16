import { describe, expect, it } from 'vitest'

import { suggestionFor, suggestionsOf } from './engine-suggest'
import type { EngineDisagreement, Inconsistency } from '../types'

function inc(over: Partial<Inconsistency> = {}): Inconsistency {
  return {
    canonical: '示例正确名',
    variant: '示例错写名',
    canonical_count: 73,
    variant_count: 3,
    pages: [90, 146, 148],
    confidence: 'high',
    ...over,
  }
}

function dis(texts: [string, string]): EngineDisagreement {
  return {
    page_no: 90,
    kind: 'char',
    severity: 'high',
    variants: [
      { engine: 'mineru', text: texts[0], label: 'MinerU' },
      { engine: 'paddleocr_vl', text: texts[1], label: 'PaddleOCR-VL' },
    ] as EngineDisagreement['variants'],
    context: '',
    anchor_hit: false,
    similarity: 0.9,
  }
}

describe('suggestionFor', () => {
  it('命中高频写法对应的低频变体时给出建议', () => {
    const s = suggestionFor('借款人 示例错写名 于2023年借款', [inc()])
    expect(s).toEqual({
      canonical: '示例正确名',
      canonicalCount: 73,
      variant: '示例错写名',
      variantCount: 3,
    })
  })

  it('只认 confidence=high：低置信度可能两个都是真实实体（两个人），不猜', () => {
    expect(suggestionFor('示例错写名', [inc({ confidence: 'low' })])).toBeNull()
    expect(suggestionFor('示例错写名', [inc({ confidence: '' })])).toBeNull()
  })

  it('文本里没有该变体时不给建议', () => {
    expect(suggestionFor('完全无关的一行', [inc()])).toBeNull()
  })

  it('空文本不给建议', () => {
    expect(suggestionFor('', [inc()])).toBeNull()
    expect(suggestionFor('   ', [inc()])).toBeNull()
  })

  it('inconsistencies 为空时不猜（多数卷宗没有重复人名）', () => {
    expect(suggestionFor('示例错写名', [])).toBeNull()
  })

  it('canonical / variant 为空的脏数据跳过', () => {
    expect(suggestionFor('x', [inc({ canonical: '' })])).toBeNull()
    expect(suggestionFor('x', [inc({ variant: '' })])).toBeNull()
  })
})

describe('suggestionsOf', () => {
  it('两侧各自命中时都返回', () => {
    const items = [
      inc({ variant: '甲某', canonical: '丙某', canonical_count: 50, variant_count: 2 }),
      inc({ variant: '乙某', canonical: '丙某', canonical_count: 50, variant_count: 4 }),
    ]
    const got = suggestionsOf(dis(['甲方是甲某', '甲方是乙某']), items)
    expect(Object.keys(got).sort()).toEqual(['mineru', 'paddleocr_vl'])
    expect(got.mineru!.canonical).toBe('丙某')
    expect(got.paddleocr_vl!.canonical).toBe('丙某')
  })

  it('两侧都没命中时返回空对象（UI 据此不渲染提示区）', () => {
    const got = suggestionsOf(dis(['无关甲', '无关乙']), [inc()])
    expect(got).toEqual({})
  })
})
