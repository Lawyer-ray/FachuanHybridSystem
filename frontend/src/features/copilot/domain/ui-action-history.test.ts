/**
 * AI 操作历史的展示口径（纯函数，node）。
 *
 * 面板的三种关键行由 `UiActionHistory.dom.test.tsx` 钉住；这里守的是**纯映射**
 * 本身：六种结局各有各的文案（`denied` / `expired` 尤其不能混成一句「失败」）、
 * 核实三态、动作中文名只从生成物取、时间只走本地时区。这些一旦漂移，DOM 测试
 * 只会看到「文案变了」，看不出变的是哪一层。
 */
import { describe, expect, it } from 'vitest'

import type { UiActionHistoryItem } from '../api-types'
import { formatHistoryTime, outcomeOf, toUiActionHistoryRow, uiActionTitle } from './ui-action-history'

function item(overrides: Partial<UiActionHistoryItem> = {}): UiActionHistoryItem {
  return {
    session_id: 's-1',
    action: 'ui_material_prep_judge',
    risk: 'confirm',
    outcome: 'ok',
    decision: 'approved',
    decided_at: '2026-11-29T09:00:00+08:00',
    verified: null,
    verify_note: '',
    approved_by_name: '',
    created_at: '2026-11-29T09:00:01+08:00',
    observed_location: '/material-prep',
    ...overrides,
  }
}

describe('toUiActionHistoryRow：结局六态', () => {
  it('六种结局各有各的文案，denied 与 expired 不混', () => {
    const labels = (['ok', 'error', 'denied', 'aborted', 'expired', 'unknown'] as const).map(
      (outcome) => toUiActionHistoryRow(item({ outcome })).outcomeLabel,
    )
    expect(labels).toEqual(['成功', '失败', '你拒绝了', '已中止', '超时未处理', '结果未知'])
    expect(new Set(labels).size).toBe(6)
  })

  it('认不出的结局值按「结果未知」展示（新后端取值不冒充成功）', () => {
    expect(outcomeOf('partial')).toBe('unknown')
    expect(toUiActionHistoryRow(item({ outcome: 'partial' })).outcomeLabel).toBe('结果未知')
  })
})

describe('toUiActionHistoryRow：核实三态', () => {
  it('verified=true → 服务端已核实', () => {
    expect(toUiActionHistoryRow(item({ verified: true })).verify).toEqual({
      kind: 'verified',
      label: '服务端已核实',
    })
  })

  it('verified=false → 页面报成功但库里没变（mismatch，渲染层据此标红）', () => {
    expect(toUiActionHistoryRow(item({ verified: false })).verify).toEqual({
      kind: 'mismatch',
      label: '页面报成功但库里没变',
    })
  })

  it('verified=null 且 outcome=ok → 未核实', () => {
    expect(toUiActionHistoryRow(item({ verified: null, outcome: 'ok' })).verify).toEqual({
      kind: 'unverified',
      label: '未核实',
    })
  })

  it('没执行到（denied/expired）不显示核实——没有「核实」可谈', () => {
    expect(toUiActionHistoryRow(item({ verified: null, outcome: 'denied' })).verify).toBeNull()
    expect(toUiActionHistoryRow(item({ verified: null, outcome: 'expired' })).verify).toBeNull()
  })
})

describe('toUiActionHistoryRow：中文名、批准人与时间', () => {
  it('动作中文名来自生成物（title），不是另抄的文案', () => {
    expect(uiActionTitle('ui_material_prep_judge')).toBe('判定材料包归属')
    expect(toUiActionHistoryRow(item()).title).toBe('判定材料包归属')
  })

  it('生成物里没有的动作名退回原文，不空着也不编一个名字', () => {
    expect(uiActionTitle('ui_from_the_future')).toBe('ui_from_the_future')
  })

  it('有批准人才显示「经 X 批准」，没有则整段不渲染', () => {
    expect(toUiActionHistoryRow(item({ approved_by_name: '王律师' })).approvedByLabel).toBe('经 王律师 批准')
    expect(toUiActionHistoryRow(item({ approved_by_name: '' })).approvedByLabel).toBe('')
  })

  it('时间按本地时区格式化；空串/坏值不渲染', () => {
    const at = formatHistoryTime('2026-11-29T09:05:00')
    expect(at).toContain('11/29')
    expect(at).toContain('09:05')
    expect(formatHistoryTime('')).toBe('')
    expect(formatHistoryTime('not-a-date')).toBe('')
  })
})
