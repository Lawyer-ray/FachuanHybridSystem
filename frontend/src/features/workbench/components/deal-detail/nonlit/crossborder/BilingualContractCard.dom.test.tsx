// @vitest-environment jsdom
/**
 * BilingualContractCard：合同正文双语对照（左英 / 右中）。
 *
 * 契约要点：
 * - 两栏按**修订块**分栏（同一个 grid 行里左右各一个块），所以高度变化同时作用于
 *   两栏、不会错行；「中文对照」关掉后只剩英文单栏
 * - 「只看修订处」过滤掉无修订的句子
 * - 高亮某条修订时，两侧都显示删除线原文（redline 的左半边）
 * - 条款索引点一下把该条第一个修订 id 交给调用方（与右侧修订清单联动）
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DEMO_NL2_CONTRACT, DEMO_REVISION_BY_ID } from '../../demo-nonlit'
import { alignClauses } from './crossborder-domain'
import { BilingualContractCard } from './BilingualContractCard'

const ROWS = alignClauses(DEMO_NL2_CONTRACT)
const CHANGED = ROWS.filter((r) => r.rev)

function setup(over: Partial<Parameters<typeof BilingualContractCard>[0]> = {}) {
  const handlers = { focusRev: null, onPickRev: vi.fn() }
  const view = render(<BilingualContractCard {...handlers} {...over} />)
  return { ...handlers, ...view }
}

describe('页头统计', () => {
  it('条数 / 句数 / 修订数是同一来源（alignClauses）', () => {
    setup()
    expect(
      screen.getByText(`${DEMO_NL2_CONTRACT.length} 条 · ${ROWS.length} 句 · ${CHANGED.length} 处修订`),
    ).toBeTruthy()
  })
})

describe('双栏', () => {
  it('默认两栏都渲染（ENGLISH / CHINESE 表头）', () => {
    setup()
    expect(screen.getByText('ENGLISH · 出租方文本')).toBeTruthy()
    expect(screen.getByText('CHINESE · 对照译文')).toBeTruthy()
  })

  it('关掉「中文对照」后只剩英文单栏', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: /中文对照/ }))
    expect(screen.getByText('ENGLISH · 出租方文本')).toBeTruthy()
    expect(screen.queryByText('CHINESE · 对照译文')).toBeNull()
  })

  it('每句一行（data-row 与 alignClauses 的行 key 一致）', () => {
    const { container } = setup()
    const keys = Array.from(container.querySelectorAll('[data-row]')).map((e) => e.getAttribute('data-row'))
    for (const r of ROWS) expect(keys).toContain(r.key)
  })
})

describe('只看修订处', () => {
  it('打开后无修订的行消失，有修订的行保留', () => {
    const { container } = setup()
    fireEvent.click(screen.getByRole('button', { name: /只看修订处/ }))
    const keys = Array.from(container.querySelectorAll('[data-row]')).map((e) => e.getAttribute('data-row'))
    for (const r of CHANGED) expect(keys).toContain(r.key)
    for (const r of ROWS.filter((x) => !x.rev)) expect(keys).not.toContain(r.key)
  })

  it('再点一次恢复全部', () => {
    const { container } = setup()
    fireEvent.click(screen.getByRole('button', { name: /只看修订处/ }))
    fireEvent.click(screen.getByRole('button', { name: /只看修订处/ }))
    expect(container.querySelectorAll('[data-row]')).toHaveLength(ROWS.length * 2)
  })
})

describe('高亮修订', () => {
  it('focusRev 命中时该行被标黄，并显示删除线原文', () => {
    const target = CHANGED[0]!
    const rev = DEMO_REVISION_BY_ID[target.rev!]!
    const { container } = setup({ focusRev: target.rev })
    const hit = container.querySelector(`[data-row="${target.key}"]`)!
    expect(hit.className).toContain('bg-status-yellow-bg/30')
    expect(screen.getAllByText(rev.original).length).toBeGreaterThan(0)
    expect(screen.getAllByText(rev.originalZh).length).toBeGreaterThan(0)
  })

  it('没有 focusRev 时不显示删除线原文', () => {
    const target = CHANGED[0]!
    const rev = DEMO_REVISION_BY_ID[target.rev!]!
    setup()
    expect(screen.queryByText(rev.original)).toBeNull()
  })
})

describe('条款索引', () => {
  it('有修订的条款标出修订数', () => {
    setup()
    const withRevs = DEMO_NL2_CONTRACT.filter((c) => c.revs.length > 0)
    // 多条条款可能同为「· 1 修订」，按出现次数断言
    for (const c of withRevs) {
      expect(screen.getAllByText(`· ${c.revs.length} 修订`).length).toBeGreaterThan(0)
    }
  })

  it('点条款 chip 把该条第一个修订 id 交给调用方', () => {
    const onPickRev = vi.fn()
    setup({ onPickRev })
    const clause = DEMO_NL2_CONTRACT.find((c) => c.revs.length > 0)!
    fireEvent.click(screen.getByText(`ART.${clause.no}`).closest('button')!)
    expect(onPickRev).toHaveBeenCalledWith(clause.revs[0])
  })

  it('无修订的条款点了不回调（保持已有选择）', () => {
    const onPickRev = vi.fn()
    setup({ onPickRev })
    const clause = DEMO_NL2_CONTRACT.find((c) => c.revs.length === 0)!
    fireEvent.click(screen.getByText(`ART.${clause.no}`).closest('button')!)
    expect(onPickRev).not.toHaveBeenCalled()
  })

  it('chip 的 title 同时给英文与中文条款名', () => {
    setup()
    const clause = DEMO_NL2_CONTRACT[0]!
    expect(screen.getByTitle(`${clause.titleEn} · ${clause.titleZh}`)).toBeTruthy()
  })
})
