// @vitest-environment jsdom
/**
 * ② 读懂面板（`UnderstandPanel`）的「点得开」那一层（jsdom）。
 *
 * - 读懂抽屉：三个视图切换，渲染视图里 markdown 标题与表格真的变成标签
 * - 读懂抽屉：换转换方法后能真的走一遍重转并出结论
 * - 关键字段：行点开能看到原文上下文与可改正的输入框，改正后回到列表生效
 * - 批量重转：全选 → 跑完 → 给结论
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import { DEMO_UNDERSTAND_FIELDS } from '../demo-data'
import { UnderstandPanel } from './UnderstandPanel'

// jsdom 下 @testing-library 不会自动 cleanup，每个用例自己挂载的树要收掉
afterEach(() => cleanup())

/** 等一段毫秒，并把期间的 setTimeout 触发的状态更新刷进 DOM（动作引擎是剧本化的 setTimeout） */
const wait = (ms: number) => act(() => new Promise<void>((r) => setTimeout(r, ms)))

describe('UnderstandPanel 细节', () => {
  it('抽屉里 markdown 三个视图可切换，渲染视图真的出标题与表格', () => {
    render(<UnderstandPanel />)

    // 第 3 份「还款明细表」的摘录里有 markdown 表格
    fireEvent.click(screen.getAllByText('查看全文')[2]!)

    const dialog = screen.getByRole('dialog')
    // 默认渲染视图：markdown 的 ## 被渲染成文档标题（不是一段等宽源码）
    expect(within(dialog).getByRole('heading', { level: 2, name: '还款明细' })).toBeTruthy()
    expect(within(dialog).getByRole('table')).toBeTruthy()

    fireEvent.click(within(dialog).getByText('源码'))
    expect(within(dialog).queryByRole('table')).toBeNull()

    fireEvent.click(within(dialog).getByText('原文对照'))
    expect(within(dialog).getByText('markdown（机器读到的）')).toBeTruthy()
    expect(within(dialog).getByText('扫描件（原件上写的）')).toBeTruthy()
    // 对照两侧都有渲染后的行：右侧扫描件那列写了「个人贷款还款明细表」
    expect(within(dialog).getByText('个人贷款还款明细表')).toBeTruthy()
  })

  it('抽屉里能切方法并真的走一遍重转', async () => {
    render(<UnderstandPanel />)

    fireEvent.click(screen.getAllByText('查看全文')[0]!)
    const dialog = screen.getByRole('dialog')

    fireEvent.click(within(dialog).getByText('表格结构还原'))
    fireEvent.click(within(dialog).getByText('用这个方法重转'))

    // 进入执行态
    expect(within(dialog).getByText(/重转中 \d+%/)).toBeTruthy()

    // 剧本跑完（总耗时约 3.3 秒，留足余量）
    await wait(9000)
    expect(within(dialog).getByText(/已用「表格结构还原」重转完成/)).toBeTruthy()
  }, 15000)

  it('关键字段行可点开，看到原文上下文并手工改正', () => {
    render(<UnderstandPanel />)

    const f = DEMO_UNDERSTAND_FIELDS[0]!
    fireEvent.click(screen.getByText(f.field))

    const dialog = screen.getByRole('dialog', { name: `${f.doc} · ${f.field}` })
    expect(within(dialog).getByText('原文上下文（命中行在中间）')).toBeTruthy()
    expect(within(dialog).getByText(/抽取口径：/)).toBeTruthy()

    const input = within(dialog).getByLabelText('手工改正（会记进字段修订历史）')
    fireEvent.change(input, { target: { value: 'DEMO-改后-001' } })
    fireEvent.click(within(dialog).getByText('保存修正'))

    // 回到列表：值被替换，并带「已改」标记
    expect(screen.getByText('DEMO-改后-001')).toBeTruthy()
    expect(screen.getByText('已改')).toBeTruthy()
  })

  it('全选后批量重转能跑完并给出结论', async () => {
    render(<UnderstandPanel />)

    fireEvent.click(screen.getByText('全选'))
    expect(screen.getByText(/已选 4 \/ 4 份/)).toBeTruthy()

    fireEvent.click(screen.getByText('批量重转 4 份'))
    await wait(5000)
    expect(screen.getByText('4 份已按当前方法重转，关键字段已重新比对')).toBeTruthy()

    fireEvent.click(screen.getByText('全不选'))
    expect(screen.getByText(/已选 0 \/ 4 份/)).toBeTruthy()
  }, 12000)
})
