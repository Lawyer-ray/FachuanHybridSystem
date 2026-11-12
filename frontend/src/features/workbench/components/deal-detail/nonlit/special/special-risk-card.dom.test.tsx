// @vitest-environment jsdom
/**
 * SpecialRiskCard / SpecialConfirmCard：风险登记表 + 客户确认记录。
 *
 * 契约要点：
 * - 风险表默认只列**未闭环**（录屏时观众要看的是「还剩几颗雷」），可切「显示已闭环」
 * - 默认展开第一条高风险（律师一进来就想看最危险的那条）
 * - 客户确认按渠道筛选；「附条件确认 / 不确认」不计入阶段完成依据
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DEMO_NL1_CLIENT_CONFIRMS, DEMO_NL1_RISKS, type DemoNl1Risk } from '../../demo-nonlit'
import { SpecialConfirmCard, SpecialRiskCard } from './special-risk-card'

describe('SpecialRiskCard', () => {
  it('页头统计：高 N 条 · 待决断 N 条 · 共 N 条', () => {
    render(<SpecialRiskCard onAssess={vi.fn()} />)
    const high = DEMO_NL1_RISKS.filter((r) => r.level === '高' && r.status !== '已闭环').length
    const pending = DEMO_NL1_RISKS.filter((r) => r.status === '待决断').length
    expect(screen.getByText(`高 ${high} 条 · 待决断 ${pending} 条 · 共 ${DEMO_NL1_RISKS.length} 条`)).toBeTruthy()
  })

  it('默认只列未闭环，切换后列出全部', () => {
    render(<SpecialRiskCard onAssess={vi.fn()} />)
    const closed = DEMO_NL1_RISKS.filter((r) => r.status === '已闭环')
    for (const r of closed) expect(screen.queryByText(r.risk)).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '显示已闭环' }))
    for (const r of DEMO_NL1_RISKS) expect(screen.getByText(r.risk)).toBeTruthy()
    expect(screen.getByRole('button', { name: '只看未闭环' })).toBeTruthy()
  })

  it('默认展开第一条高风险，再点收起', () => {
    render(<SpecialRiskCard onAssess={vi.fn()} />)
    const firstHigh = DEMO_NL1_RISKS.find((r) => r.level === '高')!
    expect(screen.getByText('影响')).toBeTruthy()
    expect(screen.getByText(firstHigh.impact)).toBeTruthy()
    fireEvent.click(screen.getByText(firstHigh.risk))
    expect(screen.queryByText(firstHigh.impact)).toBeNull()
  })

  it('展开后显示影响与应对，并给出责任人/到期', () => {
    render(<SpecialRiskCard onAssess={vi.fn()} />)
    const firstHigh = DEMO_NL1_RISKS.find((r) => r.level === '高')!
    expect(screen.getByText(firstHigh.response)).toBeTruthy()
    expect(screen.getByText(`责任人 ${firstHigh.owner} · 到期 ${firstHigh.due}`)).toBeTruthy()
  })

  it('「重新评估」把 riskId 交给调用方', () => {
    const onAssess = vi.fn()
    render(<SpecialRiskCard onAssess={onAssess} />)
    const firstHigh = DEMO_NL1_RISKS.find((r) => r.level === '高')!
    fireEvent.click(screen.getByRole('button', { name: '重新评估' }))
    expect(onAssess).toHaveBeenCalledWith(firstHigh.id)
  })

  it('没有高风险时默认不展开任何一条', () => {
    const risks: DemoNl1Risk[] = DEMO_NL1_RISKS.map((r) => ({ ...r, level: '中' as const }))
    render(<SpecialRiskCard risks={risks} onAssess={vi.fn()} />)
    expect(screen.queryByText('影响')).toBeNull()
  })

  it('全部已闭环但不显示时给「未闭环风险已清空」', () => {
    const risks: DemoNl1Risk[] = DEMO_NL1_RISKS.map((r) => ({ ...r, status: '已闭环' as const }))
    render(<SpecialRiskCard risks={risks} onAssess={vi.fn()} />)
    expect(screen.getByText('未闭环风险已清空')).toBeTruthy()
  })

  it('状态胶囊区分 待决断 / 监控中 / 已闭环', () => {
    render(<SpecialRiskCard onAssess={vi.fn()} />)
    for (const r of DEMO_NL1_RISKS.filter((x) => x.status !== '已闭环')) {
      expect(screen.getAllByText(r.status).length).toBeGreaterThan(0)
    }
  })
})

describe('SpecialConfirmCard', () => {
  it('页头统计确认数与待跟进数', () => {
    render(<SpecialConfirmCard />)
    const ok = DEMO_NL1_CLIENT_CONFIRMS.filter((r) => r.verdict === '确认').length
    const pending = DEMO_NL1_CLIENT_CONFIRMS.length - ok
    expect(screen.getByText(`确认 ${ok} 条 · 待跟进 ${pending} 条`)).toBeTruthy()
  })

  it('默认「全部」列出所有记录', () => {
    render(<SpecialConfirmCard />)
    for (const r of DEMO_NL1_CLIENT_CONFIRMS) expect(screen.getByText(r.what)).toBeTruthy()
  })

  it('按渠道筛选只留该渠道的记录', () => {
    render(<SpecialConfirmCard />)
    const channel = DEMO_NL1_CLIENT_CONFIRMS[0]!.channel
    fireEvent.click(screen.getByRole('button', { name: channel }))
    const inChannel = DEMO_NL1_CLIENT_CONFIRMS.filter((r) => r.channel === channel)
    const outChannel = DEMO_NL1_CLIENT_CONFIRMS.filter((r) => r.channel !== channel)
    for (const r of inChannel) expect(screen.getByText(r.what)).toBeTruthy()
    for (const r of outChannel) expect(screen.queryByText(r.what)).toBeNull()
  })

  it('切回「全部」恢复所有记录', () => {
    render(<SpecialConfirmCard />)
    fireEvent.click(screen.getByRole('button', { name: '邮件' }))
    fireEvent.click(screen.getByRole('button', { name: '全部' }))
    for (const r of DEMO_NL1_CLIENT_CONFIRMS) expect(screen.getByText(r.what)).toBeTruthy()
  })

  it('某渠道无记录时给空态', () => {
    const channel = DEMO_NL1_CLIENT_CONFIRMS[0]!.channel
    render(<SpecialConfirmCard records={DEMO_NL1_CLIENT_CONFIRMS.filter((r) => r.channel !== channel)} />)
    fireEvent.click(screen.getByRole('button', { name: channel }))
    expect(screen.getByText('该渠道还没有确认记录')).toBeTruthy()
  })

  it('写明推进纪律：附条件确认与不确认都不计入完成依据', () => {
    render(<SpecialConfirmCard />)
    expect(screen.getByText('推进纪律')).toBeTruthy()
    expect(
      screen.getByText('「附条件确认」与「不确认」都不计入阶段完成依据；系统在推进到下一阶段时会把它们挑出来。'),
    ).toBeTruthy()
  })
})
