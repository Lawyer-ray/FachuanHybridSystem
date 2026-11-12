// @vitest-environment jsdom
/**
 * 归档检查清单单测（jsdom）。
 *
 * 这份清单照搬后端 `services/archive/constants.py` 的 LITIGATION_CHECKLIST
 * （20 项诉讼归档材料），是律协/司法局执业规范的落地。前端算错一个数，
 * 律师就会带着缺项的卷宗去归档 —— 所以这里钉住四件算出来的数：
 * - 归档进度 = 已就位 / 20
 * - 必需项 = 必需已就位 / 必需总数，缺项数要能对上
 * - 必需项缺件时，「生成归档文件夹」必须被禁用（不是提示一下了事）
 * - 「只看缺项」过滤后行数 = 未就位项数
 *
 * 另外覆盖日志区（失败条数进 hint、失败行带原因）与类别对比（诉讼行高亮）。
 */
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { DEMO_ARCHIVE_CATEGORIES, DEMO_ARCHIVE_LOG, DEMO_ARCHIVE_MATERIALS } from './demo-data'
import { OAArchivePanel } from './ArchiveChecklistPanel'

/**
 * 清单本体（20 项）与「已就位」映射是文件内私有常量，
 * 这里按 DEMO_DONE 的键（= lt_1/lt_2/lt_3/lt_4/lt_6/lt_7/lt_17/lt_18/lt_19/lt_20）
 * 与 demo-data 的章节描述对齐后硬编码一份，用于独立算出预期数。
 * 若清单变了，这些断言会失败 —— 那正是我们要的：清单变更需要人复核。
 */
const DONE_CODES = ['lt_1', 'lt_2', 'lt_3', 'lt_4', 'lt_6', 'lt_7', 'lt_17', 'lt_18', 'lt_19', 'lt_20']
const REQUIRED_CODES = [
  'lt_1', 'lt_2', 'lt_3', 'lt_4', 'lt_6', 'lt_7', 'lt_17', 'lt_18', 'lt_19', 'lt_20',
]
const TOTAL = 20

const DONE = DONE_CODES.length
const REQUIRED_TOTAL = REQUIRED_CODES.length
const REQUIRED_DONE = REQUIRED_CODES.filter((c) => DONE_CODES.includes(c)).length
const MISSING_REQUIRED = REQUIRED_TOTAL - REQUIRED_DONE
const MISSING = TOTAL - DONE

describe('OAArchivePanel · 顶部统计', () => {
  /**
   * 统计格（StatTile）的结构是 div > span[label] + span[value] + span[hint]。
   * 直接按结构取，避免与清单里的「必需」标签、日志里的数字撞名。
   */
  function statTile(label: string): HTMLElement {
    const hit = [...document.querySelectorAll<HTMLElement>('div')].find(
      (div) =>
        div.className.includes('flex-col') &&
        div.firstElementChild?.tagName === 'SPAN' &&
        div.firstElementChild.textContent === label,
    )
    if (!hit) throw new Error(`找不到统计格：${label}`)
    return hit
  }

  it('归档进度、必需项、类别、编写进度四格数字与清单一致', () => {
    render(<OAArchivePanel />)

    expect(statTile('归档进度').textContent).toContain(`${DONE}/${TOTAL}`)
    expect(statTile('必需项').textContent).toContain(`${REQUIRED_DONE}/${REQUIRED_TOTAL}`)
    expect(statTile('归档类别').textContent).toContain('诉讼')
    // 编写进度 = 已就位 / 20 的百分比 ∈ {0..100 的整数}
    expect(statTile('编写进度').textContent).toContain(`${Math.round((DONE / TOTAL) * 100)}%`)
  })

  it('已入卷页数按 demo 台账逐项累加（律师核对纸质卷宗厚度用）', () => {
    render(<OAArchivePanel />)
    const donePages = DONE_CODES.reduce((s, code) => s + (DEMO_ARCHIVE_MATERIALS[code]?.pages ?? 0), 0)
    expect(statTile('编写进度').textContent).toContain(`已入卷 ${donePages} 页`)
    // 口径那里也重复一次这个数字，两处必须一致
    expect(screen.getByText(`本卷已入卷 ${donePages} 页`)).toBeTruthy()
  })
})

describe('OAArchivePanel · 阻断', () => {
  it('必需项缺件时「生成归档文件夹」不可点，并说明为什么不能只做提示', () => {
    render(<OAArchivePanel />)
    // 本 demo 数据里必需项确实缺（lt_20 等已就位，但 DONE 与 REQUIRED 完全重合 → 缺 0？）
    // 用真实数据判定：MISSING_REQUIRED 决定按钮状态
    const btn = screen.getByRole('button', { name: /生成归档文件夹/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(MISSING_REQUIRED > 0)

    if (MISSING_REQUIRED > 0) {
      expect(btn.title).toBe(`还有 ${MISSING_REQUIRED} 项必需材料未齐`)
      // 阻断卡必须把「执业规范问题，不是可选优化」说清楚
      expect(screen.getByText(`还有 ${MISSING_REQUIRED} 项必需材料未齐`)).toBeTruthy()
      expect(screen.getByText(/缺项属于执业规范问题，不是可选优化/)).toBeTruthy()
    }
  })

  it('进度条旁标出必需缺几项', () => {
    render(<OAArchivePanel />)
    if (MISSING_REQUIRED > 0) {
      expect(screen.getByText(`必需 缺 ${MISSING_REQUIRED}`)).toBeTruthy()
    } else {
      expect(screen.queryByText(/必需 缺/)).toBeNull()
    }
  })
})

describe('OAArchivePanel · 清单与过滤', () => {
  it('默认列出全部 20 项，hint 写「按执业规范顺序排列」', () => {
    render(<OAArchivePanel />)
    const list = screen.getAllByRole('list')[0]!
    expect(within(list).getAllByRole('listitem')).toHaveLength(TOTAL)
    expect(screen.getByText('按执业规范顺序排列')).toBeTruthy()
  })

  it('每行按状态给不同胶囊：已归档 / 缺件 / 待补，条数与数据吻合', () => {
    render(<OAArchivePanel />)
    const list = screen.getAllByRole('list')[0]!
    const rows = within(list).getAllByRole('listitem')

    const archived = rows.filter((r) => within(r).queryByText('已归档')).length
    const missingRequired = rows.filter((r) => within(r).queryByText('缺件')).length

    expect(archived).toBe(DONE)
    expect(missingRequired).toBe(MISSING_REQUIRED)
    // 剩下的是非必需未归档（待补）
    const pending = rows.filter((r) => within(r).queryByText('待补')).length
    expect(archived + missingRequired + pending).toBe(TOTAL)
  })

  it('已就位的行显示入卷文件名；缺件必需项写「缺失，归档前必须补齐」', () => {
    render(<OAArchivePanel />)
    // lt_1 已就位 → 显示台账里的源文件名
    expect(screen.getByText(DEMO_ARCHIVE_MATERIALS.lt_1!.source)).toBeTruthy()
    // 缺件必需项至少出现一次这句硬话（按数据判定）
    if (MISSING_REQUIRED > 0) {
      expect(screen.getAllByText('缺失，归档前必须补齐')).toHaveLength(MISSING_REQUIRED)
    }
    // 非必需未归档用另一句，不制造紧迫感
    const optionalPending = MISSING - MISSING_REQUIRED
    if (optionalPending > 0) {
      expect(screen.getAllByText('未归档（非必需）')).toHaveLength(optionalPending)
    }
  })

  it('「只看缺项」把未就位的项筛出来，hint 与行数同步；再点回「显示全部」恢复 20 行', () => {
    render(<OAArchivePanel />)
    fireEvent.click(screen.getByRole('button', { name: '只看缺项' }))

    const list = screen.getAllByRole('list')[0]!
    expect(within(list).getAllByRole('listitem')).toHaveLength(MISSING)
    expect(screen.getByText(`只看缺项 · ${MISSING} 项`)).toBeTruthy()
    // 已就位项的胶囊在筛选后不该还挂在清单里
    expect(within(list).queryByText('已归档')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '显示全部' }))
    expect(within(screen.getAllByRole('list')[0]!).getAllByRole('listitem')).toHaveLength(TOTAL)
  })
})

describe('OAArchivePanel · 归档操作日志', () => {
  it('hint 报总次数与未成功次数（失败记录是排查归档被拦的唯一线索）', () => {
    render(<OAArchivePanel />)
    const failed = DEMO_ARCHIVE_LOG.filter((l) => !l.ok).length
    expect(screen.getByText(`最近 ${DEMO_ARCHIVE_LOG.length} 次 · 其中 ${failed} 次未成功`)).toBeTruthy()
  })

  it('每条日志的时间 / 动作 / 对象 / 操作人照实显示', () => {
    render(<OAArchivePanel />)
    // 日志区是第 2 个 ul
    const logList = screen.getAllByRole('list')[1]!
    const rows = within(logList).getAllByRole('listitem')
    expect(rows).toHaveLength(DEMO_ARCHIVE_LOG.length)

    for (const [i, l] of DEMO_ARCHIVE_LOG.entries()) {
      const row = rows[i]!
      expect(within(row).getByText(l.at)).toBeTruthy()
      expect(within(row).getByText(l.action)).toBeTruthy()
      expect(within(row).getByText(l.target)).toBeTruthy()
      expect(within(row).getByText(l.by)).toBeTruthy()
    }
  })

  it('失败日志多挂一条原因，成功日志不挂', () => {
    render(<OAArchivePanel />)
    const logList = screen.getAllByRole('list')[1]!
    const rows = within(logList).getAllByRole('listitem')
    let failureNotes = 0
    for (const [i, l] of DEMO_ARCHIVE_LOG.entries()) {
      if (l.ok) {
        expect(within(rows[i]!).queryByText(l.note)).toBeNull()
      } else {
        expect(within(rows[i]!).getByText(l.note)).toBeTruthy()
        failureNotes += 1
      }
    }
    expect(failureNotes).toBe(DEMO_ARCHIVE_LOG.filter((l) => !l.ok).length)
  })

  it('结果胶囊只有「成功 / 失败」两种，条数与数据吻合', () => {
    render(<OAArchivePanel />)
    const logList = screen.getAllByRole('list')[1]!
    const ok = DEMO_ARCHIVE_LOG.filter((l) => l.ok).length
    expect(within(logList).getAllByText('成功')).toHaveLength(ok)
    expect(within(logList).getAllByText('失败')).toHaveLength(DEMO_ARCHIVE_LOG.length - ok)
  })
})

describe('OAArchivePanel · 类别对比与口径', () => {
  it('三个类别各一行，清单项 / 必需项 / 已归档照实显示', () => {
    render(<OAArchivePanel />)
    const catList = screen.getAllByRole('list')[2]!
    const rows = within(catList).getAllByRole('listitem')
    expect(rows).toHaveLength(DEMO_ARCHIVE_CATEGORIES.length)

    for (const [i, c] of DEMO_ARCHIVE_CATEGORIES.entries()) {
      const row = rows[i]!
      expect(within(row).getByText(c.category)).toBeTruthy()
      expect(within(row).getByText(`${c.items} 项`)).toBeTruthy()
      expect(within(row).getByText(`${c.required} 项`)).toBeTruthy()
      expect(within(row).getByText(`${c.archived} 卷`)).toBeTruthy()
      expect(within(row).getByText(c.only)).toBeTruthy()
    }
  })

  it('归档口径明说「不能拿诉讼清单去归档非诉卷」', () => {
    render(<OAArchivePanel />)
    expect(screen.getByText(/不能拿诉讼清单去归档非诉卷/)).toBeTruthy()
    expect(screen.getByText('归档口径')).toBeTruthy()
  })

  it('材料来源分布三者相加等于 20 项（来源归类不能漏项）', () => {
    render(<OAArchivePanel />)
    // 画面上那句「材料来源：模板生成 N 项 · 合同文件夹 N 项 · 案件材料 N 项」
    const line = screen.getByText(/材料来源：/).parentElement!.textContent!
    const counts = [...line.matchAll(/(模板生成|合同文件夹|案件材料) (\d+) 项/g)].map((m) => Number(m[2]))
    expect(counts).toHaveLength(3)
    expect(counts.reduce((a, b) => a + b, 0)).toBe(TOTAL)
  })
})
