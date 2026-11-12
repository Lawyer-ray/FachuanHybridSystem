/**
 * bank-litigation/utils 单测（node 环境）。
 *
 * 这两个函数都不碰 React，但都在关键路径上：
 * - fmtMoney 给法院看的金额，**绝不允许走浮点**（千万级会丢精度）
 * - suggestMbid 决定要素式文书默认用哪套模板，认不出时要保守回落
 */
import { describe, expect, it } from 'vitest'

import { fmtMoney, suggestMbid } from './utils'

describe('fmtMoney', () => {
  it('空值统一显示破折号，不显示 0（"没有金额"与"金额为 0"是两件事）', () => {
    expect(fmtMoney(null)).toBe('—')
    expect(fmtMoney(undefined)).toBe('—')
  })

  it('整数按千分位切分，小数部分原样保留', () => {
    expect(fmtMoney('1234567')).toBe('1,234,567')
    expect(fmtMoney('1234567.89')).toBe('1,234,567.89')
    expect(fmtMoney('100')).toBe('100')
    expect(fmtMoney('999')).toBe('999')
    expect(fmtMoney('0')).toBe('0')
  })

  it('千位边界：三位以下不加逗号，四位起才切', () => {
    expect(fmtMoney('999')).toBe('999')
    expect(fmtMoney('1000')).toBe('1,000')
    expect(fmtMoney('1000000')).toBe('1,000,000')
  })

  it('超长 Decimal 字符串逐位照搬 —— 不经 Number，因此不丢精度', () => {
    // Number('12345678901234567.89') 会变成 12345678901234568，
    // 这正是本函数存在的理由，所以拿一个超过 MAX_SAFE_INTEGER 的串做断言。
    expect(fmtMoney('12345678901234567')).toBe('12,345,678,901,234,567')
    expect(fmtMoney('12345678901234567.89')).toBe('12,345,678,901,234,567.89')
  })

  it('数字入参按字符串走同一套规则', () => {
    expect(fmtMoney(1234567)).toBe('1,234,567')
    expect(fmtMoney(1234.5)).toBe('1,234.5')
  })

  it('负数只切整数部分，负号留在最前', () => {
    // '-1234' 的整数段是 '-1234'，正则从右侧三位一断，得到 '-1,234'
    expect(fmtMoney('-1234')).toBe('-1,234')
  })
})

describe('suggestMbid', () => {
  it('按案由关键词选模板：民间借贷 / 买卖 / 信用卡 各归各的', () => {
    expect(suggestMbid('民间借贷纠纷')).toBe('mjjdqsz')
    expect(suggestMbid('买卖合同纠纷')).toBe('lhjfqsz')
    expect(suggestMbid('信用卡纠纷')).toBe('xykqsz')
  })

  it('金融借款与「借款合同」都归金融借款起诉状', () => {
    expect(suggestMbid('金融借款合同纠纷')).toBe('jrjkqsz')
    expect(suggestMbid('借款合同纠纷')).toBe('jrjkqsz')
  })

  it('认不出时保守回落到金融借款起诉状，而不是空串', () => {
    // 本场景主案由就是金融借款；给个空模板号会让下拉框整列空掉
    expect(suggestMbid('财产损害赔偿纠纷')).toBe('jrjkqsz')
    expect(suggestMbid('')).toBe('jrjkqsz')
    expect(suggestMbid(null)).toBe('jrjkqsz')
    expect(suggestMbid(undefined)).toBe('jrjkqsz')
  })

  it('关键词优先于兜底：同一串里出现多个案由时先命中先返回', () => {
    // 判断顺序是 民间借贷 → 买卖 → 信用卡 → 金融借款
    expect(suggestMbid('民间借贷（买卖担保）')).toBe('mjjdqsz')
  })
})
