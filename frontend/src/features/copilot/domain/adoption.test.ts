/**
 * 采纳记录映射（node 环境）。
 *
 * 锁两件会静默说错话的事：
 * - `lane === null && merged === false` 不是"采纳了空栏"，而是**没有有效采纳**；
 * - `adopted_at` 原样透传（时区/格式不该由映射层决定）。
 */

import { describe, expect, it } from 'vitest'

import type { ReviewAdoptionWire } from './adoption'
import { adoptionSummary, toAdoptionView } from './adoption'

const wire = (over: Partial<ReviewAdoptionWire> = {}): ReviewAdoptionWire => ({
  review_id: 'rv-1',
  lane: 'pi',
  merged: false,
  note: '',
  adopted_at: '2026-11-21T08:30:00+08:00',
  ...over,
})

describe('toAdoptionView：线上记录 → 视图', () => {
  it('采纳某一栏：lane/merged/note 原样映射', () => {
    expect(toAdoptionView(wire({ note: '引用了第 7 条，最贴题' }))).toEqual({
      reviewId: 'rv-1',
      lane: 'pi',
      merged: false,
      note: '引用了第 7 条，最贴题',
      adoptedAt: '2026-11-21T08:30:00+08:00',
    })
  })

  it('adopted_at 原样透传，不本地格式化（时区不在映射层决定）', () => {
    const view = toAdoptionView(wire({ adopted_at: '2026-11-21T00:30:00Z' }))
    expect(view?.adoptedAt).toBe('2026-11-21T00:30:00Z')
  })

  it('没有记录（GET 返回 null）→ null', () => {
    expect(toAdoptionView(null)).toBeNull()
    expect(toAdoptionView(undefined)).toBeNull()
  })

  it('lane=null + merged=true = 标为合并（有效采纳）', () => {
    expect(toAdoptionView(wire({ lane: null, merged: true }))).toEqual({
      reviewId: 'rv-1',
      lane: null,
      merged: true,
      note: '',
      adoptedAt: '2026-11-21T08:30:00+08:00',
    })
  })

  it('lane=null + merged=false 视为没有有效采纳（不是"采纳了空栏"）', () => {
    expect(toAdoptionView(wire({ lane: null, merged: false }))).toBeNull()
  })

  it('空串栏只可能是脏数据：归一到 null，再按同一条规则判定', () => {
    expect(toAdoptionView(wire({ lane: '', merged: false }))).toBeNull()
    expect(toAdoptionView(wire({ lane: '', merged: true }))?.lane).toBeNull()
  })
})

describe('adoptionSummary：回显文案', () => {
  const view = (over: Partial<ReviewAdoptionWire> = {}) => toAdoptionView(wire(over))!

  it('采纳某一栏：显示栏头显示名（labelOf 决定翻不翻）', () => {
    const adoption = view({ lane: 'dsh' })
    expect(adoptionSummary(adoption, (lane) => (lane === 'dsh' ? 'DeepSeek Harness' : lane))).toBe(
      '已采纳 DeepSeek Harness',
    )
  })

  it('lane=null + merged=true → 合并采纳，不出现空栏名', () => {
    const text = adoptionSummary(view({ lane: null, merged: true }))
    expect(text).toBe('已标为合并采纳')
    expect(text).not.toContain('null')
  })
})
