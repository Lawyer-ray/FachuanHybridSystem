// @vitest-environment jsdom
/**
 * OA 立案展示组件测试（jsdom）。
 *
 * 这三张表是「机器填了什么、以前立得怎么样、失败了怎么办」的唯一呈现，
 * 覆盖点：
 * - 历史立案记录：行数、状态文案、退回行能在表里被读出来
 * - 字段映射：条目数与「手工补录」这类非机器取值有标出来
 * - 站点清单：后端有站点时照实显示名字并带演示统计；无站点时回落演示清单
 * - 常见失败原因：自动重试 / 需人工 两类都出现在画面上
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { DEMO_OA_FIELD_MAPPING, DEMO_OA_FILING_LOG, DEMO_OA_HISTORY, DEMO_OA_SITES } from '../demo-data'
import { OAFailureCauses } from './OAFailureCauses'
import { OAFieldMapping } from './OAFieldMapping'
import { OAHistoryTable } from './OAHistoryTable'
import { OASiteList } from './OASiteList'

describe('OAHistoryTable', () => {
  it('列出全部历史立案记录，并显示已立案/退回计数', () => {
    render(<OAHistoryTable />)
    const rows = within(screen.getByRole('table')).getAllByRole('row')
    // 表头 1 行 + 数据行
    expect(rows).toHaveLength(DEMO_OA_HISTORY.length + 1)

    const filed = DEMO_OA_HISTORY.filter((r) => r.state === 'filed').length
    const returned = DEMO_OA_HISTORY.filter((r) => r.state === 'returned').length
    expect(screen.getByText(`近 ${DEMO_OA_HISTORY.length} 次 · 已立案 ${filed} · 退回 ${returned}`)).toBeTruthy()

    expect(screen.getAllByText('已立案')).toHaveLength(filed)
    expect(screen.getAllByText('已退回')).toHaveLength(returned)
    // 金额逐行照实显示（千分位口径）
    expect(screen.getByText('¥998,670.21')).toBeTruthy()
  })
})

describe('OAFieldMapping', () => {
  it('列出全部字段映射，并标出非机器确定的取值来源', () => {
    render(<OAFieldMapping />)
    const rows = within(screen.getByRole('table')).getAllByRole('row')
    expect(rows).toHaveLength(DEMO_OA_FIELD_MAPPING.length + 1)
    expect(screen.getByText('标的额')).toBeTruthy()
    expect(screen.getByText('争议标的金额')).toBeTruthy()

    const manual = DEMO_OA_FIELD_MAPPING.filter((m) => m.source === 'manual').length
    expect(screen.getAllByText('手工补录')).toHaveLength(manual)
  })
})

describe('OASiteList', () => {
  it('后端有站点时照实显示站点名与凭证状态，并按下标补演示统计', () => {
    const onPick = vi.fn()
    render(
      <OASiteList
        sites={[{ id: 'abc', name: '某某律所OA', hasCredential: true }]}
        currentName="某某律所OA"
        onPick={onPick}
      />,
    )
    expect(screen.getByText('某某律所OA')).toBeTruthy()
    expect(screen.getByText('已配凭证')).toBeTruthy()
    expect(screen.getByText(`本月 ${DEMO_OA_SITES[0]!.filedThisMonth} 件`)).toBeTruthy()

    fireEvent.click(screen.getByRole('button'))
    expect(onPick).toHaveBeenCalledWith('某某律所OA')
  })

  it('后端没站点时回落演示清单', () => {
    render(<OASiteList sites={[]} currentName="" onPick={() => {}} />)
    const rows = screen.getAllByRole('listitem')
    expect(rows).toHaveLength(DEMO_OA_SITES.length)
    expect(within(rows[0]!).getByText(DEMO_OA_SITES[0]!.name)).toBeTruthy()
    // 未配凭证的站点在演示清单里也要如实标红
    expect(screen.getAllByText('未配凭证').length).toBeGreaterThan(0)
  })
})

describe('OAFailureCauses', () => {
  it('每类失败都给出了处置方式：自动重试与需人工都出现', () => {
    render(<OAFailureCauses />)
    const rows = within(screen.getByRole('table')).getAllByRole('row')
    expect(rows).toHaveLength(6 + 1)
    expect(screen.getByText('凭证过期')).toBeTruthy()
    expect(screen.getByText('页面改版')).toBeTruthy()
    expect(screen.getAllByText('自动重试').length).toBeGreaterThan(0)
    expect(screen.getAllByText('需人工').length).toBeGreaterThan(0)
  })
})

describe('DEMO_OA_FILING_LOG', () => {
  it('12 步里恰好一次失败，且紧跟一步成功的重试', () => {
    expect(DEMO_OA_FILING_LOG.length).toBe(12)
    expect(DEMO_OA_FILING_LOG.filter((l) => !l.ok)).toHaveLength(1)
    expect(DEMO_OA_FILING_LOG.some((l) => l.stage === '重试' && l.ok)).toBe(true)
  })
})
