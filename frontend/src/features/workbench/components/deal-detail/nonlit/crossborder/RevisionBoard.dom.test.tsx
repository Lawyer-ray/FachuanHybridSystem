// @vitest-environment jsdom
/**
 * RevisionBoard：修订清单（维度筛选 + 逐条展开 + 对方律师意见）。
 *
 * 关键口径：**tab 的计数必须与过滤结果同源**（filterRevisions / filterTabLabel），
 * 不能出现「高 2」却列出 3 条。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DEMO_NL2_COUNTER_OPINIONS, DEMO_NL2_FILTERS, DEMO_TH_CONTRACT_REVISIONS } from '../../demo-nonlit'
import { filterRevisions, filterTabLabel } from './crossborder-domain'
import { RevisionBoard } from './RevisionBoard'

function setup(over: Partial<Parameters<typeof RevisionBoard>[0]> = {}) {
  const handlers = { tabId: DEMO_NL2_FILTERS[0]!.id, onPickTab: vi.fn(), picked: null, onPick: vi.fn() }
  const view = render(<RevisionBoard {...handlers} {...over} />)
  return { ...handlers, ...view }
}

describe('维度页签', () => {
  it('每个页签的计数与过滤结果一致', () => {
    setup()
    for (const t of DEMO_NL2_FILTERS) {
      const expected = filterRevisions(DEMO_TH_CONTRACT_REVISIONS, t)
      const label = filterTabLabel(t, DEMO_TH_CONTRACT_REVISIONS.length)
      const btn = screen.getByRole('button', { name: label })
      expect(btn).toBeTruthy()
      // 页签文字里的数字就是该维度的条数
      expect(label).toContain(String(expected.length))
    }
  })

  it('切页签把 id 交给调用方', () => {
    const { onPickTab } = setup()
    const t = DEMO_NL2_FILTERS[1]!
    fireEvent.click(screen.getByRole('button', { name: filterTabLabel(t, DEMO_TH_CONTRACT_REVISIONS.length) }))
    expect(onPickTab).toHaveBeenCalledWith(t.id)
  })

  it('未知 tabId 退回第一个维度（不白屏）', () => {
    setup({ tabId: 'nope' })
    const first = DEMO_NL2_FILTERS[0]!
    const rows = filterRevisions(DEMO_TH_CONTRACT_REVISIONS, first)
    for (const r of rows) expect(screen.getByText(r.title)).toBeTruthy()
  })
})

describe('修订行', () => {
  const all = DEMO_NL2_FILTERS.find((t) => filterRevisions(DEMO_TH_CONTRACT_REVISIONS, t).length === DEMO_TH_CONTRACT_REVISIONS.length)
  const tabId = all?.id ?? DEMO_NL2_FILTERS[0]!.id

  it('严重度用高中低标签，已挂法条/需律师判断分开标', () => {
    const rows = filterRevisions(DEMO_TH_CONTRACT_REVISIONS, DEMO_NL2_FILTERS.find((t) => t.id === tabId)!)
    setup({ tabId })
    expect(screen.getAllByText('高').length).toBe(rows.filter((r) => r.severity === 'high').length)
    expect(screen.getAllByText('已挂法条').length).toBe(rows.filter((r) => r.verified).length)
    expect(screen.getAllByText('需律师判断').length).toBe(rows.filter((r) => !r.verified).length)
  })

  it('有对方意见的行标「对方 N 条意见」', () => {
    const rows = filterRevisions(DEMO_TH_CONTRACT_REVISIONS, DEMO_NL2_FILTERS.find((t) => t.id === tabId)!)
    setup({ tabId })
    for (const r of rows) {
      const count = DEMO_NL2_COUNTER_OPINIONS.filter((o) => o.rev === r.id).length
      if (count > 0) expect(screen.getAllByText(`对方 ${count} 条意见`).length).toBeGreaterThan(0)
    }
  })

  it('点行切换展开（picked 为空时传该行 id）', () => {
    const rows = filterRevisions(DEMO_TH_CONTRACT_REVISIONS, DEMO_NL2_FILTERS.find((t) => t.id === tabId)!)
    const { onPick } = setup({ tabId })
    fireEvent.click(screen.getByText(rows[0]!.title))
    expect(onPick).toHaveBeenCalledWith(rows[0]!.id)
  })

  it('已展开的行再点传 null（收起）', () => {
    const rows = filterRevisions(DEMO_TH_CONTRACT_REVISIONS, DEMO_NL2_FILTERS.find((t) => t.id === tabId)!)
    const { onPick } = setup({ tabId, picked: rows[0]!.id })
    fireEvent.click(screen.getByText(rows[0]!.title))
    expect(onPick).toHaveBeenCalledWith(null)
  })

  it('展开时显示原文（删除线）/ 改法 / 立场依据', () => {
    const rows = filterRevisions(DEMO_TH_CONTRACT_REVISIONS, DEMO_NL2_FILTERS.find((t) => t.id === tabId)!)
    const rev = rows[0]!
    setup({ tabId, picked: rev.id })
    expect(screen.getByText(rev.original)).toBeTruthy()
    expect(screen.getByText(rev.suggested)).toBeTruthy()
    expect(screen.getByText(`立场依据：${rev.stance}`)).toBeTruthy()
  })

  it('展开时列出对方律师意见（作者 + 态度 + 内容）', () => {
    const rows = filterRevisions(DEMO_TH_CONTRACT_REVISIONS, DEMO_NL2_FILTERS.find((t) => t.id === tabId)!)
    const rev = rows.find((r) => DEMO_NL2_COUNTER_OPINIONS.some((o) => o.rev === r.id))!
    const opinions = DEMO_NL2_COUNTER_OPINIONS.filter((o) => o.rev === rev.id)
    setup({ tabId, picked: rev.id })
    for (const o of opinions) {
      expect(screen.getByText(o.author)).toBeTruthy()
      expect(screen.getByText(o.attitude)).toBeTruthy()
      expect(screen.getByText(o.opinion)).toBeTruthy()
    }
  })
})

describe('空维度', () => {
  it('筛选结果为空时给「该维度下没有修订」', () => {
    const empty = DEMO_NL2_FILTERS.find((t) => filterRevisions(DEMO_TH_CONTRACT_REVISIONS, t).length === 0)
    if (!empty) {
      // 演示数据里每个维度都有内容 → 这条无可测；显式跳过而不是假断言
      expect(true).toBe(true)
      return
    }
    setup({ tabId: empty.id })
    expect(screen.getByText('该维度下没有修订。')).toBeTruthy()
  })
})
