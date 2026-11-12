// @vitest-environment jsdom
/**
 * 整包分段页的展示组件（jsdom）。
 *
 * 这些件在 idle 态负责回答「上一次拆成什么样、这包引擎认得出什么」：
 * - StepBar：四步关节，当前步反色、已过步绿色、未到步灰 —— 位置感全靠它
 * - SegmentsTable：复核表的行数据（页码区间 / 类型 / 置信度 / 复核标记）
 * - HistoryTable：45 天内的拆分记录，结果三态 + 需复核段数 + 是否归案
 * - TemplateWall：识别能力墙（本月次数与平均置信度，偏低类要点名）
 * - SegmentSnapshot：上一包的明细快照（页码区间与判定依据）
 * - RuleBook / FaqList：规则与常见问题（折叠块）
 */
import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { PdfSplitSegment } from '../../api'
import {
  DEMO_BUNDLE_CAPABILITIES,
  DEMO_BUNDLE_FAQ,
  DEMO_BUNDLE_RULES,
  DEMO_BUNDLE_SEGMENT_DETAIL,
  DEMO_BUNDLE_SPLIT_RECORDS,
} from '../demo-data'
import { HistoryTable } from './HistoryTable'
import { FaqList, RuleBook } from './RuleBook'
import { SegmentsTable } from './SegmentsTable'
import { StepBar, type BundlePhase } from './StepBar'
import { SegmentSnapshot, TemplateWall } from './TemplateWall'

describe('StepBar', () => {
  it('四步关节都渲染，且当前阶段对应的那一步是反色高亮（bg-foreground）', () => {
    const cases: Array<[BundlePhase, string]> = [
      ['uploading', '识别'],
      ['splitting', '识别'],
      ['review', '复核'],
      ['confirming', '复核'],
      ['importing', '归案'],
      ['done', '完成'],
    ]

    for (const [phase, label] of cases) {
      const { unmount } = render(<StepBar phase={phase} />)
      // 四步标签按固定顺序出现
      for (const step of ['识别', '复核', '归案', '完成']) expect(screen.getByText(step)).toBeTruthy()
      expect(screen.getByText(label).className).toContain('bg-foreground')
      unmount()
    }
  })

  it('已过步骤用绿色，未到的步骤用弱化色', () => {
    render(<StepBar phase="importing" />)
    // importing 是第 3 步 → 前两步已过（status-green），第 4 步未到（muted）
    expect(screen.getByText('识别').className).toContain('text-status-green')
    expect(screen.getByText('复核').className).toContain('text-status-green')
    expect(screen.getByText('归案').className).toContain('bg-foreground')
    expect(screen.getByText('完成').className).toContain('text-muted-foreground')
  })

  it('idle / failed 不属于任何一步：四步都不高亮，也不误标已过', () => {
    for (const phase of ['idle', 'failed'] as BundlePhase[]) {
      const { unmount } = render(<StepBar phase={phase} />)
      for (const step of ['识别', '复核', '归案', '完成']) {
        const el = screen.getByText(step)
        expect(el.className).not.toContain('bg-foreground')
        expect(el.className).not.toContain('text-status-green')
      }
      unmount()
    }
  })
})

describe('SegmentsTable', () => {
  const segs: PdfSplitSegment[] = [
    {
      id: 1,
      order: 1,
      page_start: 1,
      page_end: 4,
      segment_type: 'complaint',
      filename: '01_民事起诉状.pdf',
      segment_label: '民事起诉状',
      confidence: 0.96,
      review_flag: 'ok',
    },
    {
      id: 2,
      order: 2,
      page_start: 5,
      page_end: 5,
      segment_type: 'unknown',
      filename: '02_送达地址确认书.pdf',
      segment_label: '送达地址确认书',
      confidence: 0.72,
      review_flag: 'low_confidence',
    },
    {
      id: 3,
      order: 3,
      page_start: 6,
      page_end: 6,
      segment_type: 'other',
      filename: '03_未识别.pdf',
      segment_label: '其他材料',
      confidence: null,
      review_flag: 'unrecognized',
    },
  ] as PdfSplitSegment[]

  it('单页段只写页号，跨页段写区间', () => {
    render(<SegmentsTable segs={segs} />)
    expect(screen.getByText('1-4')).toBeTruthy()
    // 5-5 收敛成 5
    expect(screen.getByText('5')).toBeTruthy()
    expect(screen.queryByText('5-5')).toBeNull()
  })

  it('置信度两位小数；没有置信度写破折号，不写 0.00', () => {
    render(<SegmentsTable segs={segs} />)
    expect(screen.getByText('0.96')).toBeTruthy()
    expect(screen.getByText('0.72')).toBeTruthy()
    expect(screen.getByText('—')).toBeTruthy()
  })

  it('复核标记三态各有文案：正常 / 需复核 / 未识别', () => {
    render(<SegmentsTable segs={segs} />)
    expect(screen.getAllByText('正常')).toHaveLength(1)
    expect(screen.getByText('需复核')).toBeTruthy()
    expect(screen.getByText('未识别')).toBeTruthy()
  })

  it('每行都带文件名与识别出的材料类型', () => {
    render(<SegmentsTable segs={segs} />)
    for (const s of segs) {
      expect(screen.getByText(s.filename)).toBeTruthy()
      expect(screen.getByText(s.segment_label!)).toBeTruthy()
    }
  })

  it('没有分段时只剩表头，不渲染任何数据行', () => {
    render(<SegmentsTable segs={[]} />)
    expect(screen.getByText('文件名')).toBeTruthy()
    expect(screen.queryByText('民事起诉状')).toBeNull()
  })
})

describe('HistoryTable', () => {
  it('hint 报记录条数、合计页数与合计份数', () => {
    render(<HistoryTable />)
    const pages = DEMO_BUNDLE_SPLIT_RECORDS.reduce((s, r) => s + r.pages, 0)
    const materials = DEMO_BUNDLE_SPLIT_RECORDS.reduce((s, r) => s + r.materials, 0)
    expect(
      screen.getByText(
        `最近 ${DEMO_BUNDLE_SPLIT_RECORDS.length} 包 · 合计 ${pages.toLocaleString('zh-CN')} 页 / ${materials} 份`,
      ),
    ).toBeTruthy()
  })

  it('每条记录一行，文件名 / 页份 / 方式 / 时间都在', () => {
    render(<HistoryTable />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(DEMO_BUNDLE_SPLIT_RECORDS.length)

    for (const [i, r] of DEMO_BUNDLE_SPLIT_RECORDS.entries()) {
      const row = items[i]!
      expect(within(row).getByText(r.fileName)).toBeTruthy()
      expect(within(row).getByText(`${r.pages} / ${r.materials}`)).toBeTruthy()
      expect(within(row).getByText(r.at)).toBeTruthy()
      expect(within(row).getByText(r.mode === 'content' ? '内容识别' : '分隔页')).toBeTruthy()
    }
  })

  it('结果三态：已确认 / 需复核 / 未识别，逐行与数据吻合', () => {
    render(<HistoryTable />)
    const TEXT = { confirmed: '已确认', review: '需复核', unrecognized: '未识别' } as const
    const items = screen.getAllByRole('listitem')
    for (const [i, r] of DEMO_BUNDLE_SPLIT_RECORDS.entries()) {
      const row = items[i]!
      // 一行只挂一个结果胶囊，「需复核」这个字在别处（列头/其它列）不该串进来
      expect(within(row).getAllByText(TEXT[r.result])).toHaveLength(1)
    }
  })

  it('案由把「合同纠纷 / 纠纷」后缀去掉再显示（列窄，留着尾巴挤掉正文）', () => {
    render(<HistoryTable />)
    // 「金融借款合同纠纷」→「金融借款」
    expect(screen.getAllByText('金融借款').length).toBeGreaterThan(0)
    expect(screen.queryByText('金融借款合同纠纷')).toBeNull()
  })

  it('需复核段数为 0 显示破折号；归案份数为 0 显示「未归案」', () => {
    render(<HistoryTable />)
    const items = screen.getAllByRole('listitem')
    const noFlag = DEMO_BUNDLE_SPLIT_RECORDS.filter((r) => r.flagged === 0).length
    const notImported = DEMO_BUNDLE_SPLIT_RECORDS.filter((r) => r.imported === 0).length

    expect(within(items[0]!).getAllByText('—').length).toBeGreaterThanOrEqual(0)
    // 计数断言：全表里「—」出现次数 ≥ 无标记条数（同格可能有别的破折号）
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(noFlag)
    expect(screen.getAllByText('未归案')).toHaveLength(notImported)
  })
})

describe('TemplateWall', () => {
  it('四个统计格：类型数 / 本月拆分 / 平均置信度 / 易错类数', () => {
    render(<TemplateWall />)
    const monthTotal = DEMO_BUNDLE_CAPABILITIES.reduce((s, c) => s + c.monthCount, 0)
    const low = DEMO_BUNDLE_CAPABILITIES.filter((c) => c.avgConfidence < 0.8)
    const avg = (
      DEMO_BUNDLE_CAPABILITIES.reduce((s, c) => s + c.avgConfidence, 0) / DEMO_BUNDLE_CAPABILITIES.length
    ).toFixed(2)

    expect(screen.getByText(`本模板支持 ${DEMO_BUNDLE_CAPABILITIES.length} 类材料 · 本月共拆 ${monthTotal} 份`)).toBeTruthy()
    expect(screen.getByText(`${monthTotal} 份`)).toBeTruthy()
    // 「平均置信度」这个数字也可能与下面某类材料的置信度同值（如 0.90），
    // 所以用「标签 → 相邻数值」定位统计格，而不是全局 getByText。
    const avgLabel = screen.getByText('平均置信度')
    expect(avgLabel.parentElement!.textContent).toContain(avg)
    // 易错类型数按 avgConfidence < 0.8 统计
    expect(screen.getByText(`${low.length} 类`)).toBeTruthy()
  })

  it('每类材料一行，带本月次数与两位小数的平均置信度', () => {
    render(<TemplateWall />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(DEMO_BUNDLE_CAPABILITIES.length)
    for (const [i, c] of DEMO_BUNDLE_CAPABILITIES.entries()) {
      const row = items[i]!
      expect(within(row).getByText(c.label)).toBeTruthy()
      expect(within(row).getByText(`本月 ${c.monthCount} 次`)).toBeTruthy()
      expect(within(row).getByText(c.avgConfidence.toFixed(2))).toBeTruthy()
    }
  })

  it('置信度分档配色：≥0.9 绿、≥0.8 灰、<0.8 黄（易错类要能被一眼挑出）', () => {
    render(<TemplateWall />)
    const items = screen.getAllByRole('listitem')
    for (const [i, c] of DEMO_BUNDLE_CAPABILITIES.entries()) {
      const score = within(items[i]!).getByText(c.avgConfidence.toFixed(2))
      const expected =
        c.avgConfidence >= 0.9
          ? 'text-status-green'
          : c.avgConfidence >= 0.8
            ? 'text-muted-foreground'
            : 'text-status-yellow'
      expect(score.className).toContain(expected)
    }
  })

  it('底部把置信度偏低的类型点名列出（复核时重点看这几类）', () => {
    render(<TemplateWall />)
    const low = DEMO_BUNDLE_CAPABILITIES.filter((c) => c.avgConfidence < 0.8)
    expect(screen.getByText(new RegExp(`${low.map((c) => c.label).join('、')} 平均置信度偏低`))).toBeTruthy()
  })
})

describe('SegmentSnapshot', () => {
  it('hint 报段数与需复核段数', () => {
    render(<SegmentSnapshot />)
    const flagged = DEMO_BUNDLE_SEGMENT_DETAIL.filter((d) => d.flag !== 'ok').length
    expect(screen.getByText(`${DEMO_BUNDLE_SEGMENT_DETAIL.length} 段`)).toBeTruthy()
    expect(screen.getByText(`${flagged} 段需复核`)).toBeTruthy()
  })

  it('每段一行：序号补零、页码区间、文件名、判定依据、置信度、复核标记', () => {
    render(<SegmentSnapshot />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(DEMO_BUNDLE_SEGMENT_DETAIL.length)

    for (const [i, d] of DEMO_BUNDLE_SEGMENT_DETAIL.entries()) {
      const row = items[i]!
      expect(within(row).getByText(String(d.order).padStart(2, '0'))).toBeTruthy()
      expect(within(row).getByText(`P${d.pageStart}–${d.pageEnd}`)).toBeTruthy()
      expect(within(row).getByText(d.filename)).toBeTruthy()
      expect(within(row).getByText(`依据：${d.evidence}`)).toBeTruthy()
      expect(within(row).getByText(d.confidence.toFixed(2))).toBeTruthy()
    }
  })

  it('复核标记三态文案与数据吻合', () => {
    render(<SegmentSnapshot />)
    const count = (f: string) => DEMO_BUNDLE_SEGMENT_DETAIL.filter((d) => d.flag === f).length
    expect(screen.getAllByText('正常')).toHaveLength(count('ok'))
    expect(screen.getAllByText('需复核')).toHaveLength(count('low_confidence'))
    expect(screen.getAllByText('未识别')).toHaveLength(count('unrecognized'))
  })

  it('置信度分档配色：≥0.9 绿、≥0.75 次色、<0.75 红', () => {
    render(<SegmentSnapshot />)
    const items = screen.getAllByRole('listitem')
    for (const [i, d] of DEMO_BUNDLE_SEGMENT_DETAIL.entries()) {
      const score = within(items[i]!).getByText(d.confidence.toFixed(2))
      const expected =
        d.confidence >= 0.9
          ? 'text-status-green'
          : d.confidence >= 0.75
            ? 'text-secondary-foreground'
            : 'text-status-red'
      expect(score.className).toContain(expected)
    }
  })
})

describe('RuleBook', () => {
  it('每条规则一段：标题 / 正文 / 示例', () => {
    render(<RuleBook />)
    expect(screen.getByText('拆分规则')).toBeTruthy()
    for (const rule of DEMO_BUNDLE_RULES) {
      expect(screen.getByText(rule.title)).toBeTruthy()
      expect(screen.getByText(rule.body)).toBeTruthy()
      expect(screen.getByText(rule.example)).toBeTruthy()
    }
  })
})

describe('FaqList', () => {
  it('每条常见问题一个折叠块，问题和答案都在 DOM 里（靠 details 控制显隐）', () => {
    render(<FaqList />)
    expect(screen.getByText('常见问题')).toBeTruthy()
    for (const item of DEMO_BUNDLE_FAQ) {
      expect(screen.getByText(item.q)).toBeTruthy()
      expect(screen.getByText(item.a)).toBeTruthy()
    }
    expect(document.querySelectorAll('details')).toHaveLength(DEMO_BUNDLE_FAQ.length)
  })
})
