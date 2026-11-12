// @vitest-environment jsdom
/**
 * 一张网立案页的四张展示表（jsdom）。
 *
 * 这四张表是「递交前必须核对一遍」的东西，错一个字都会让律师带着错数据去递：
 * - AmountCheckTable：三处金额并排，不一致的行标红并给出差异说明
 * - FieldMappingTable：机器替人填了什么，拿不准的标「待确认」并写原因
 * - MaterialList：页数 / 盖章 / 上传时间三列分开（盖了没传照样递不了）
 * - SubmitHistory：同一案多次递交的历史，退回与失败能一眼数出来
 *
 * 数据全部来自 demo-data（纯展示组件，无 props、无网络）。
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import {
  DEMO_COURT_AMOUNT_CHECK,
  DEMO_COURT_FIELD_MAPPING,
  DEMO_COURT_MATERIALS,
  DEMO_COURT_SUBMIT_HISTORY,
} from '../demo-data'
import { AmountCheckTable } from './AmountCheckTable'
import { FieldMappingTable } from './FieldMappingTable'
import { MaterialList } from './MaterialList'
import { SubmitHistory } from './SubmitHistory'

/** 取表体行（去掉表头） */
function bodyRows() {
  return within(screen.getByRole('table')).getAllByRole('row').slice(1)
}

describe('AmountCheckTable', () => {
  it('每行一个金额项，三列标的额逐格照实显示', () => {
    render(<AmountCheckTable />)
    const rows = bodyRows()
    expect(rows).toHaveLength(DEMO_COURT_AMOUNT_CHECK.length)

    // 逐行核对：同一数值可能在同一行出现多次（本金三处都是 820,000.00），
    // 所以用 queryAllByText 的条数来断言，而不是 getByText。
    for (const [i, r] of DEMO_COURT_AMOUNT_CHECK.entries()) {
      const row = rows[i]!
      expect(within(row).getAllByText(r.item)).toHaveLength(1)
      for (const amount of [r.fromPleading, r.fromCourtForm, r.fromElement]) {
        expect(within(row).queryAllByText(amount).length).toBeGreaterThan(0)
      }
    }
  })

  it('一致的行写「一致」，不一致的行给出差异说明并按失败数标红胶囊', () => {
    render(<AmountCheckTable />)
    const failed = DEMO_COURT_AMOUNT_CHECK.filter((r) => !r.ok)
    const passed = DEMO_COURT_AMOUNT_CHECK.filter((r) => r.ok)

    expect(screen.getAllByText('一致')).toHaveLength(passed.length)
    for (const r of failed) expect(screen.getByText(r.diff!)).toBeTruthy()

    // 表头 hint 报「N/total 一致」，胶囊报「N 项不一致」
    const consistent = DEMO_COURT_AMOUNT_CHECK.length - failed.length
    expect(screen.getByText(new RegExp(`${consistent}/${DEMO_COURT_AMOUNT_CHECK.length} 一致`))).toBeTruthy()
    expect(screen.getByText(`${failed.length} 项不一致`)).toBeTruthy()
  })
})

describe('FieldMappingTable', () => {
  it('列出全部映射，法穿字段名与一张网字段名成对出现', () => {
    render(<FieldMappingTable />)
    const rows = bodyRows()
    expect(rows).toHaveLength(DEMO_COURT_FIELD_MAPPING.length)

    // 「案件名称」这类字段法穿侧与一张网侧同名，同一行会命中两次
    for (const [i, r] of DEMO_COURT_FIELD_MAPPING.entries()) {
      const row = rows[i]!
      expect(within(row).queryAllByText(r.from).length).toBeGreaterThan(0)
      expect(within(row).queryAllByText(r.to).length).toBeGreaterThan(0)
    }
  })

  it('待确认的行带「待确认」标签和一句原因；已映射的行标「已映射」', () => {
    render(<FieldMappingTable />)
    const pending = DEMO_COURT_FIELD_MAPPING.filter((r) => r.status === 'confirm')
    const mapped = DEMO_COURT_FIELD_MAPPING.filter((r) => r.status === 'mapped')

    expect(pending.length).toBeGreaterThan(0)
    expect(screen.getAllByText('待确认')).toHaveLength(pending.length)
    expect(screen.getAllByText('已映射')).toHaveLength(mapped.length)

    // 每个待确认项都写清了「为什么机器拿不准」
    for (const r of pending) {
      expect(r.note).toBeTruthy()
      expect(screen.getByText(r.note!)).toBeTruthy()
    }
  })

  it('顶部胶囊报待确认条数，hint 报已映射/总数', () => {
    render(<FieldMappingTable />)
    const pending = DEMO_COURT_FIELD_MAPPING.filter((r) => r.status === 'confirm').length
    const mapped = DEMO_COURT_FIELD_MAPPING.length - pending

    expect(screen.getByText(`${pending} 项待确认`)).toBeTruthy()
    expect(screen.getByText(new RegExp(`${mapped}/${DEMO_COURT_FIELD_MAPPING.length} 已映射`))).toBeTruthy()
  })
})

describe('MaterialList', () => {
  it('逐行显示材料名 / 页数 / 盖章状态 / 上传时间', () => {
    render(<MaterialList />)
    const rows = bodyRows()
    expect(rows).toHaveLength(DEMO_COURT_MATERIALS.length)

    for (const [i, r] of DEMO_COURT_MATERIALS.entries()) {
      const row = rows[i]!
      expect(within(row).getByText(r.name)).toBeTruthy()
      expect(within(row).getByText(String(r.pages))).toBeTruthy()
      // 未上传的格子写「未上传」，不是空白
      expect(within(row).getByText(r.uploadedAt ?? '未上传')).toBeTruthy()
    }
  })

  it('盖章状态三种文案各自出现在对应行', () => {
    render(<MaterialList />)
    const count = (s: string) => DEMO_COURT_MATERIALS.filter((r) => r.stamp === s).length
    expect(screen.getAllByText('已盖章')).toHaveLength(count('stamped'))
    expect(screen.getAllByText('部分盖章')).toHaveLength(count('partial'))
    expect(screen.getAllByText('未盖章')).toHaveLength(count('none'))
  })

  it('hint 报总份数 / 总页数 / 已上传比 —— 盖了章没上传是最常见的漏交', () => {
    render(<MaterialList />)
    const pages = DEMO_COURT_MATERIALS.reduce((s, r) => s + r.pages, 0)
    const uploaded = DEMO_COURT_MATERIALS.filter((r) => r.uploadedAt).length
    const hint = `共 ${DEMO_COURT_MATERIALS.length} 份 · ${pages} 页 · 已上传 ${uploaded}/${DEMO_COURT_MATERIALS.length}`
    expect(screen.getByText(hint)).toBeTruthy()
  })
})

describe('SubmitHistory', () => {
  it('时间倒序一行一次递交，批次号与受理号逐行照实显示', () => {
    render(<SubmitHistory />)
    const rows = bodyRows()
    expect(rows).toHaveLength(DEMO_COURT_SUBMIT_HISTORY.length)

    for (const [i, r] of DEMO_COURT_SUBMIT_HISTORY.entries()) {
      const row = rows[i]!
      expect(within(row).getByText(r.at)).toBeTruthy()
      expect(within(row).getByText(r.batch)).toBeTruthy()
      expect(within(row).getByText(r.receipt)).toBeTruthy()
    }
    // 渲染顺序与 demo 数据的顺序一致（数据本身已按时间倒序）
    expect(rows[0]!.textContent).toContain(DEMO_COURT_SUBMIT_HISTORY[0]!.batch)
  })

  it('四种结果各有不同文案，且条数与数据吻合', () => {
    render(<SubmitHistory />)
    const count = (s: string) => DEMO_COURT_SUBMIT_HISTORY.filter((r) => r.result === s).length

    expect(screen.getAllByText('已受理')).toHaveLength(count('accepted'))
    expect(screen.getAllByText('法院退回')).toHaveLength(count('returned'))
    expect(screen.getAllByText('递交失败')).toHaveLength(count('failed'))
    expect(screen.getAllByText('待处理')).toHaveLength(count('pending'))
  })

  it('hint 把「共几次 · 已受理几 · 退回几」直接报出来（退回原因是律师最想知道的）', () => {
    render(<SubmitHistory />)
    const accepted = DEMO_COURT_SUBMIT_HISTORY.filter((r) => r.result === 'accepted').length
    const returned = DEMO_COURT_SUBMIT_HISTORY.filter((r) => r.result === 'returned').length
    expect(
      screen.getByText(`共 ${DEMO_COURT_SUBMIT_HISTORY.length} 次 · 已受理 ${accepted} · 退回 ${returned}`),
    ).toBeTruthy()
  })
})
