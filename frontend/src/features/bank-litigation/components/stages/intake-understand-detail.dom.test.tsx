// @vitest-environment jsdom
/**
 * ① 收案 / ② 读懂 的「点得开」那一层（jsdom）。
 *
 * 覆盖点都是演示时必须真的能点的地方：
 * - 收案抽屉：扫描件能翻页（页码 1/3 → 2/3）、识别框文字能读到、置信度因子可展开
 * - 收案面板：源文件行内剔除会实时改总页数；「追加材料」弹窗能切三种来源
 * - 读懂抽屉：三个视图切换，渲染视图里 markdown 标题与表格真的变成标签
 * - 读懂抽屉：换转换方法后能真的走一遍重转并出结论
 * - 关键字段：行点开能看到原文上下文与可改正的输入框，改正后回到列表生效
 */
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import {
  DEMO_INTAKE_SOURCES,
  DEMO_UNDERSTAND_FIELDS,
  DEMO_X1_CONFIDENCE_FACTORS,
  DEMO_X1_SEGMENT_PREVIEWS,
} from '../demo-data'
import { IntakePanel } from './IntakePanel'
import { UnderstandPanel } from './UnderstandPanel'

// jsdom 下 @testing-library 不会自动 cleanup，每个用例自己挂载的树要收掉
afterEach(() => cleanup())

/** 等一段毫秒，并把期间的 setTimeout 触发的状态更新刷进 DOM（动作引擎是剧本化的 setTimeout） */
const wait = (ms: number) => act(() => new Promise<void>((r) => setTimeout(r, ms)))

describe('IntakePanel 细节', () => {
  it('抽屉里扫描件可翻页，并列出识别框', async () => {
    render(<IntakePanel />)

    fireEvent.click(screen.getByText('个人购房借款担保合同'))

    const preview = DEMO_X1_SEGMENT_PREVIEWS.find((p) => p.seq === 1)!
    const dialog = within(screen.getByRole('dialog'))
    expect(dialog.getByText(`第 1 页 / 共 ${preview.pages.length} 页`)).toBeTruthy()
    // 第 1 页的两个识别框文字（框上 hover 提示 + 下方清单各一份）
    for (const box of preview.pages[0]!.boxes) expect(dialog.getAllByText(box.label).length).toBe(2)

    fireEvent.click(dialog.getByTitle('下一页'))
    expect(dialog.getByText(`第 2 页 / 共 ${preview.pages.length} 页`)).toBeTruthy()
    // 识别框文案里有全角空格，getByText 会把连续空白规范化，故用函数匹配
    const label = preview.pages[1]!.boxes[0]!.label
    expect(dialog.getAllByText((_, el) => el?.textContent?.replace(/\s/g, '') === label.replace(/\s/g, '')).length).toBe(2)
    // 第 1 页的识别框已随翻页消失
    expect(dialog.queryByText(preview.pages[0]!.boxes[0]!.label)).toBeNull()

    // 到末页后「下一页」禁用
    fireEvent.click(dialog.getByTitle('下一页'))
    expect((dialog.getByTitle('下一页') as HTMLButtonElement).disabled).toBe(true)
    // 翻回上一页
    fireEvent.click(dialog.getByTitle('上一页'))
    expect(screen.getByText(`第 2 页 / 共 ${preview.pages.length} 页`)).toBeTruthy()
  })

  it('抽屉里「为什么是 98%」可展开，列出 4 个因子与合计分', () => {
    render(<IntakePanel />)

    fireEvent.click(screen.getByText('个人购房借款担保合同'))

    const factors = DEMO_X1_CONFIDENCE_FACTORS.filter((f) => f.seq === 1)
    const total = factors.reduce((n, f) => n + f.score, 0)
    // 未展开时因子明细不在页面上
    expect(screen.queryByText(factors[0]!.label)).toBeNull()

    fireEvent.click(screen.getByText(`为什么是 ${total}%`))
    for (const f of factors) expect(screen.getByText(f.label)).toBeTruthy()
    expect(screen.getAllByText(`${total} 分`).length).toBeGreaterThan(0)
  })

  it('源文件行内可剔除，剔除后总页数实时减少', () => {
    render(<IntakePanel />)
    const totalPages = DEMO_INTAKE_SOURCES.reduce((n, f) => n + f.pages, 0)
    expect(screen.getByText(`${totalPages}`)).toBeTruthy()

    const target = DEMO_INTAKE_SOURCES[0]!
    // 6 个源文件各有一对按钮，取第一个（借款合同.pdf，14 页）
    fireEvent.click(screen.getAllByTitle('从整包里剔除（不进后续阶段）')[0]!)

    expect(screen.getByText(`${totalPages - target.pages}`)).toBeTruthy()
    expect(screen.getAllByTitle('恢复这个源文件')).toHaveLength(1)

    // 恢复后页数回来
    fireEvent.click(screen.getByTitle('恢复这个源文件'))
    expect(screen.getByText(`${totalPages}`)).toBeTruthy()
  })

  it('「追加材料」弹窗能在三种来源间切换', () => {
    render(<IntakePanel />)

    fireEvent.click(screen.getByText('追加材料'))
    const dialog = screen.getByRole('dialog', { name: '追加材料' })
    const scopers = within(dialog)

    // 默认「从客户链接」：能看到待取清单
    expect(scopers.getByRole('button', { name: /从客户链接/ })).toBeTruthy()
    expect(scopers.getByText('催收记录_补充_2025Q3-Q4.pdf · 6 页 · 10-30 09:20')).toBeTruthy()

    fireEvent.click(scopers.getByRole('button', { name: /从本地上传/ }))
    expect(scopers.getByText('可一次多选，单个 ≤ 50 MB')).toBeTruthy()

    fireEvent.click(scopers.getByRole('button', { name: /从邮箱拉取/ }))
    expect(scopers.getByText('扫描件-不动产权证 · 1 个附件 · 11-01 10:05')).toBeTruthy()
  })
})

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
