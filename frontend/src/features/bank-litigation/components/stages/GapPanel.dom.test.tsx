// @vitest-environment jsdom
/**
 * ③ 缺件面板（`GapPanel`）的交互测试（jsdom）。
 *
 * 细节都藏在交互里，只看渲染出来的字不够：
 * - 来源分组过滤、勾选批量操作、话术编辑后回显、抽屉里的客户往来时间线
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  DEMO_GAP_NOTICES,
  DEMO_X2_GAP_SCRIPTS,
  DEMO_X2_GAP_SOURCES,
  DEMO_X2_GAP_TIMELINE,
} from '../demo-data'
import { GapPanel } from './GapPanel'

describe('GapPanel · 客户往来时间线', () => {
  it('点开一条缺件，抽屉里给出这条缺件的完整沟通过程，每条带渠道与时间', () => {
    render(<GapPanel />)
    // 同一句话在「缺件清单」和「客户补回来的材料」里各出现一次，点清单那一行
    fireEvent.click(screen.getAllByText('催收记录（2025 年后）')[0]!)

    const drawer = screen.getByRole('dialog')
    const events = DEMO_X2_GAP_TIMELINE.filter((t) => t.item === '催收记录（2025 年后）')
    expect(within(drawer).getByText(`客户往来时间线（${events.length} 条）`)).toBeTruthy()
    // 首条（系统检测）与末条（重跑缺件检测）都在画面上
    expect(within(drawer).getByText('检测到缺件，生成补件清单')).toBeTruthy()
    expect(within(drawer).getByText('重跑缺件检测')).toBeTruthy()
    // 每条事件的时刻都照实显示
    for (const at of new Set(events.map((e) => e.at))) {
      expect(within(drawer).getAllByText(at).length).toBeGreaterThan(0)
    }
    // 渠道标签（短信 / 邮件 / 客户 / 系统）逐条带出来
    expect(within(drawer).getAllByText('短信').length).toBeGreaterThan(0)
    expect(within(drawer).getAllByText('客户').length).toBeGreaterThan(0)
  })
})

describe('GapPanel · 来源分组', () => {
  it('切到「担保类」只剩担保类缺件，再切回「全部」恢复全量', () => {
    render(<GapPanel />)
    const suretyship = DEMO_X2_GAP_SOURCES.filter((s) => s.source === '担保类').map((s) => s.item)

    fireEvent.click(screen.getByRole('button', { name: /^担保类/ }))
    // 只看清单列表：已补齐的项在「客户补回来的材料」那张卡里仍会显示
    const listAfter = () => screen.getAllByRole('list')[0]!
    expect(within(listAfter()).getByText(suretyship[0]!)).toBeTruthy()
    for (const g of DEMO_GAP_NOTICES.filter((n) => !suretyship.includes(n.item))) {
      expect(within(listAfter()).queryByText(g.item)).toBeNull()
    }

    fireEvent.click(screen.getByRole('button', { name: /^全部/ }))
    for (const g of DEMO_GAP_NOTICES) {
      expect(within(listAfter()).getByText(g.item)).toBeTruthy()
    }
  })
})

describe('GapPanel · 勾选与批量操作', () => {
  it('全选后可批量催办，回执按勾选条数给出', async () => {
    render(<GapPanel />)
    // 只勾一条「还没补齐」的硬阻塞项
    fireEvent.click(screen.getByRole('button', { name: '勾选 抵押物权属证明' }))
    expect(screen.getByText('已选 1 项')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '批量催办' }))
    const note = await screen.findByText(/已批量催办 1 项：抵押物权属证明/, undefined, { timeout: 5000 })
    expect(note).toBeTruthy()
  })

  it('没勾选时批量按钮不可点', () => {
    render(<GapPanel />)
    expect((screen.getByRole('button', { name: '批量催办' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: '批量标记已收' }) as HTMLButtonElement).disabled).toBe(true)
  })
})

describe('GapPanel · 话术可编辑', () => {
  it('编辑话术后保存，卡片上回显新话术并标「已改过」，可恢复默认', () => {
    render(<GapPanel />)
    const first = DEMO_X2_GAP_SCRIPTS[0]!
    fireEvent.click(screen.getAllByRole('button', { name: /编辑话术/ })[0]!)

    const textarea = screen.getByLabelText(`编辑「${first.title}」话术`) as HTMLTextAreaElement
    expect(textarea.value).toBe(first.body)
    fireEvent.change(textarea, { target: { value: '【定制】请于 3 日内补齐：{list}' } })
    fireEvent.click(screen.getByRole('button', { name: '保存' }))

    expect(screen.getByText('【定制】请于 3 日内补齐：{list}')).toBeTruthy()
    expect(screen.getByText('已改过')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '恢复默认' }))
    expect(screen.queryByText('【定制】请于 3 日内补齐：{list}')).toBeNull()
    expect(screen.getByText(first.body)).toBeTruthy()
  })
})
