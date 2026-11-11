// @vitest-environment jsdom
/**
 * LawGateCard：外国法核验依据（四道闸 + 法条原文）。
 *
 * 这张卡存在的意义是把「AI 查了法条」与「AI 编了法条」在界面上区分开：
 * 三道规则闸（法是否存在 / 有没有正文 / 条款号在不在范围）不过，判断层就不执行。
 * 因此断言集中在：未跑核验时不落结论、点开某道闸能看到「查了什么 / 拿回来什么」、
 * 法条原文页签每条都能回查对应修订。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DEMO_LAW_GATES, DEMO_NL2_LAW_EXCERPTS } from '../../demo-nonlit'
import { LawGateCard } from './LawGateCard'

describe('未跑核验时', () => {
  it('给出「还没跑核验」说明，不假装有结论', () => {
    render(<LawGateCard active={false} onPickRev={vi.fn()} />)
    expect(screen.getByText(/还没跑核验。点上面的「核验法条」后/)).toBeTruthy()
  })

  it('四道闸仍然列出来（让人知道要过几道）', () => {
    render(<LawGateCard active={false} onPickRev={vi.fn()} />)
    for (const g of DEMO_LAW_GATES) expect(screen.getByText(g.name)).toBeTruthy()
  })

  it('跑过之后不再显示那段说明', () => {
    render(<LawGateCard active onPickRev={vi.fn()} />)
    expect(screen.queryByText(/还没跑核验/)).toBeNull()
  })
})

describe('四道闸', () => {
  it('页签上是闸的总数', () => {
    render(<LawGateCard active onPickRev={vi.fn()} />)
    expect(screen.getByRole('button', { name: `四道闸 ${DEMO_LAW_GATES.length}` })).toBeTruthy()
  })

  it('规则闸与判断层用不同标签区分', () => {
    render(<LawGateCard active onPickRev={vi.fn()} />)
    expect(screen.getAllByText('规则闸').length).toBe(DEMO_LAW_GATES.filter((g) => g.kind === 'rule').length)
    expect(screen.getAllByText('判断层').length).toBe(DEMO_LAW_GATES.filter((g) => g.kind !== 'rule').length)
  })

  it('点开某道闸显示「查了什么 / 拿回来什么 / 原始样本」', () => {
    render(<LawGateCard active onPickRev={vi.fn()} />)
    const gate = DEMO_LAW_GATES[0]!
    fireEvent.click(screen.getByText(gate.name))
    expect(screen.getByText(/^Q: 是否存在名为「泰国民商法典」的法律？/)).toBeTruthy()
    expect(screen.getByText(/^A: 命中 1 部。/)).toBeTruthy()
    expect(screen.getByText(/registry: TH-CCC-1952/)).toBeTruthy()
  })

  it('再点一次收起', () => {
    render(<LawGateCard active onPickRev={vi.fn()} />)
    const gate = DEMO_LAW_GATES[0]!
    fireEvent.click(screen.getByText(gate.name))
    fireEvent.click(screen.getByText(gate.name))
    expect(screen.queryByText(/^Q: 是否存在名为「泰国民商法典」的法律？/)).toBeNull()
  })

  it('同一时刻只展开一道闸', () => {
    render(<LawGateCard active onPickRev={vi.fn()} />)
    fireEvent.click(screen.getByText(DEMO_LAW_GATES[0]!.name))
    fireEvent.click(screen.getByText(DEMO_LAW_GATES[1]!.name))
    expect(screen.queryByText(/^Q: 是否存在名为「泰国民商法典」的法律？/)).toBeNull()
    expect(screen.getByText(/^Q: 该法能否取到逐条正文/)).toBeTruthy()
  })
})

describe('法条原文页签', () => {
  it('切过去后每条 excerpt 都显示法名/条号/英文原文/出处', () => {
    render(<LawGateCard active onPickRev={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`法条原文 ${DEMO_NL2_LAW_EXCERPTS.length}`) }))
    const first = DEMO_NL2_LAW_EXCERPTS[0]!
    expect(screen.getByText(`${first.law} ${first.article}`)).toBeTruthy()
    expect(screen.getByText(`“${first.textEn}”`)).toBeTruthy()
    // 出处行按 excerpt 条数重复出现（原文可能共用同一来源）
    expect(screen.getAllByText(new RegExp(`出处：${first.source}`)).length).toBeGreaterThan(0)
    expect(screen.getAllByText('已核验')).toHaveLength(DEMO_NL2_LAW_EXCERPTS.length)
  })

  it('「看对应修订」把 rev id 交回调用方（与修订清单联动）', () => {
    const onPickRev = vi.fn()
    render(<LawGateCard active onPickRev={onPickRev} />)
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`法条原文 ${DEMO_NL2_LAW_EXCERPTS.length}`) }))
    const first = DEMO_NL2_LAW_EXCERPTS[0]!
    fireEvent.click(screen.getAllByText(/看对应修订：/)[0]!)
    expect(onPickRev).toHaveBeenCalledWith(first.rev)
  })

  it('明确标出「第 5 处无外国法依据」，不硬编法条', () => {
    render(<LawGateCard active onPickRev={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`法条原文 ${DEMO_NL2_LAW_EXCERPTS.length}`) }))
    expect(screen.getByText('第 5 处无外国法依据')).toBeTruthy()
    expect(screen.getByText(/不硬编法条。/)).toBeTruthy()
  })

  it('切回四道闸', () => {
    render(<LawGateCard active onPickRev={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`法条原文 ${DEMO_NL2_LAW_EXCERPTS.length}`) }))
    fireEvent.click(screen.getByRole('button', { name: `四道闸 ${DEMO_LAW_GATES.length}` }))
    expect(screen.getByText(DEMO_LAW_GATES[0]!.name)).toBeTruthy()
  })
})
