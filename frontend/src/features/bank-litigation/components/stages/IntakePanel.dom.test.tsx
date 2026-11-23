// @vitest-environment jsdom
/**
 * ① 收案面板（`IntakePanel`）的「点得开」那一层（jsdom）。
 *
 * - 收案抽屉：扫描件能翻页（页码 1/3 → 2/3）、识别框文字能读到、置信度因子可展开
 * - 收案面板：源文件行内剔除会实时改总页数；「追加材料」弹窗能切三种来源
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'

import {
  DEMO_INTAKE_SOURCES,
  DEMO_X1_CONFIDENCE_FACTORS,
  DEMO_X1_SEGMENT_PREVIEWS,
} from '../demo-data'
import { IntakePanel } from './IntakePanel'

// jsdom 下 @testing-library 不会自动 cleanup，每个用例自己挂载的树要收掉
afterEach(() => cleanup())

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
