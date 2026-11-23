// @vitest-environment jsdom
/**
 * ④ 文书面板（`ContractPanel`）单测（jsdom）。
 *
 * - 生成的文书：每行有模板下拉，默认 v3.2，可切 v2.8
 * - 利冲：导出报告走进度并落一个 PDF 名
 * - 条款逐条审核：抽屉里编辑后列表回显「已修改」
 * - 机器人的执行录像从这里能打开
 */
import { act, fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DEMO_CONTRACT_GEN, DEMO_CONTRACT_TERMS, DEMO_X3_BROWSER_FRAMES } from '../demo-data'
import { ContractPanel } from './ContractPanel'

describe('ContractPanel', () => {
  it('生成的委托材料每行可切模板', () => {
    render(<ContractPanel />)
    const selects = screen.getAllByRole('combobox')
    expect(selects).toHaveLength(DEMO_CONTRACT_GEN.length)

    const first = selects[0]!
    expect((first as HTMLSelectElement).value).toBe('v3.2')
    fireEvent.change(first, { target: { value: 'v2.8' } })
    expect((first as HTMLSelectElement).value).toBe('v2.8')
    // 右栏回显「换了模板的文书」
    expect(screen.getByText('v2.8', { selector: 'span' })).toBeTruthy()
  })

  it('点「导出利冲报告」后走进度并提示已生成 PDF', async () => {
    vi.useFakeTimers()
    render(<ContractPanel />)
    fireEvent.click(screen.getByRole('button', { name: '导出利冲报告' }))
    expect(screen.getByRole('button', { name: '生成中…' })).toBeTruthy()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(8000)
    })
    expect(screen.getByText(/已生成 PDF：LCA-20261101-0007/)).toBeTruthy()
    vi.useRealTimers()
  })

  it('抽屉里逐条编辑条款，保存后列表回显「已修改」', () => {
    render(<ContractPanel />)

    const clause = DEMO_CONTRACT_TERMS.find((t) => !t.filled)!.clause
    const row = screen.getByText(clause).closest('li')!
    fireEvent.click(within(row).getByRole('button', { name: /编辑/ }))

    fireEvent.change(screen.getByRole('textbox'), { target: { value: '代为和解、代收款项及执行款' } })
    fireEvent.click(screen.getByRole('button', { name: '保存修改' }))

    const updated = screen.getByText(clause).closest('li')!
    expect(within(updated).getByText('已修改')).toBeTruthy()
    expect(within(updated).getByText('代为和解、代收款项及执行款')).toBeTruthy()
    expect(within(updated).queryByText('未填')).toBeNull()
  })

  it('点「查看执行录像」打开录像抽屉', () => {
    render(<ContractPanel />)
    fireEvent.click(screen.getByRole('button', { name: /查看执行录像/ }))
    expect(screen.getByText(/第 1 \/ 5 帧/)).toBeTruthy()
    expect(screen.getByText(DEMO_X3_BROWSER_FRAMES[0]!.url)).toBeTruthy()
  })
})
