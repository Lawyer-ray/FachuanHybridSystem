// @vitest-environment jsdom
/**
 * ReadinessPanel（立案前判断面板）单测。
 *
 * 锁住四条行为，每条都对应一个真实的误读后果：
 * 1) blocked 的结论必须是**一句话人话**（「现在还不能出，缺 N 项」），缺口按
 *    必须补 / 影响金额 / 影响胜诉 分组，每条带 为什么 / 向谁要 / 形式——
 *    少一样，律师就得回头问「这条到底找谁拿」；
 * 2) ready 就是「材料齐，可以直接出」，不许硬凑出一份缺口清单；
 * 3) unknown 显示「判断没跑成功」+ warnings 原文，**不能**长得像材料齐全；
 * 4) 复制清单是纯文本的「标题 + 分组 + 条目」，律师能整段发给委托人/助理。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const copyTextMock = vi.hoisted(() => vi.fn<(text: string) => Promise<boolean>>(async () => true))

vi.mock('@/lib/clipboard', () => ({ copyText: copyTextMock }))

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { toast } from 'sonner'

import type { DraftAssessResult } from '../types'
import { ReadinessPanel } from './ReadinessPanel'

function assess(over: Partial<DraftAssessResult> = {}): DraftAssessResult {
  return {
    verdict: 'blocked',
    profile_key: 'lease_arrears',
    matrix: [
      {
        requirement_key: 'payment_due',
        requirement: '付款义务与到期日',
        why: '无到期日就无法认定逾期',
        fact: '',
        source: '',
        status: 'missing',
      },
      {
        requirement_key: 'parties',
        requirement: '被告身份',
        why: '立案需明确被告',
        fact: '黎某，身份证号 4401…',
        source: '土地分包合同书 首部',
        status: 'met',
      },
    ],
    missing_materials: [
      {
        item: '被告身份证复印件或户籍信息',
        why: '立案需明确被告并送达',
        from_whom: '委托人 / 律师调查',
        form: '复印件 / 公安查询单',
        severity: 'blocking',
      },
      {
        item: '欠款对账与银行流水',
        why: '影响欠款金额认定',
        from_whom: '委托人',
        form: '银行流水',
        severity: 'amount',
      },
      {
        item: '律师函送达凭证',
        why: '影响解除通知是否到达的抗辩',
        from_whom: '委托人',
        form: '快递底单',
        severity: 'defense',
      },
    ],
    questions: [
      { to: '委托人经办人', question: '2026 年 6 月的管理维护费是否已缴？', why: '律师函只列 7-12 月' },
    ],
    blocking: ['被告身份证复印件或户籍信息'],
    warnings: [],
    ...over,
  }
}

beforeEach(() => {
  copyTextMock.mockClear()
  copyTextMock.mockResolvedValue(true)
  vi.mocked(toast.success).mockClear()
  vi.mocked(toast.error).mockClear()
})

describe('ReadinessPanel：blocked', () => {
  it('结论是一句话，缺口按三档分组并带 为什么 / 向谁要 / 形式', () => {
    render(<ReadinessPanel result={assess()} />)

    expect(screen.getByTestId('readiness-verdict').textContent).toBe('现在还不能出，缺 1 项')

    // 分组标题带条数，顺序就是处理顺序
    expect(screen.getByText('必须补 · 1')).toBeTruthy()
    expect(screen.getByText('影响金额 · 1')).toBeTruthy()
    expect(screen.getByText('影响胜诉 · 1')).toBeTruthy()

    // 每条：item + why + 向谁要 + 形式
    expect(screen.getByText('被告身份证复印件或户籍信息')).toBeTruthy()
    expect(screen.getByText('立案需明确被告并送达')).toBeTruthy()
    expect(screen.getByText('向委托人 / 律师调查要 · 形式：复印件 / 公安查询单')).toBeTruthy()

    // 问题清单逐条可读（问什么 + 问谁 / 为什么问）
    expect(screen.getByText('2026 年 6 月的管理维护费是否已缴？')).toBeTruthy()
    expect(screen.getByText('问委托人经办人 · 律师函只列 7-12 月')).toBeTruthy()
  })

  it('不把后端字段名摆给律师看（verdict / severity / profile_key 不外露）', () => {
    render(<ReadinessPanel result={assess()} />)

    const text = screen.getByTestId('readiness-panel').textContent ?? ''
    expect(text).not.toContain('blocked')
    expect(text).not.toContain('severity')
    expect(text).not.toContain('lease_arrears')
  })
})

describe('ReadinessPanel：ready / unknown', () => {
  it('ready 说「材料齐，可以直接出」，没有缺口就不硬凑清单', () => {
    render(
      <ReadinessPanel
        result={assess({ verdict: 'ready', missing_materials: [], questions: [], blocking: [] })}
      />,
    )

    expect(screen.getByTestId('readiness-verdict').textContent).toBe('材料齐，可以直接出')
    expect(screen.queryByText(/必须补/)).toBeNull()
    expect(screen.queryByText(/要核实的问题/)).toBeNull()
  })

  it('draftable_with_gaps 说「能出，但有 N 处会在成稿里留空」，N 数的是会留空的要件', () => {
    const missingRow = (key: string) => ({
      requirement_key: key,
      requirement: key,
      why: '',
      fact: '',
      source: '',
      status: 'missing',
    })
    render(
      <ReadinessPanel
        result={assess({ verdict: 'draftable_with_gaps', matrix: [missingRow('a'), missingRow('b'), missingRow('c')] })}
      />,
    )

    expect(screen.getByTestId('readiness-verdict').textContent).toBe('能出，但有 3 处会在成稿里留空')
  })

  it('unknown 说「判断没跑成功」并给 warnings 原文，不显示成材料齐', () => {
    const warning = '模型返回的不是合法结构，本轮判断作废'
    render(<ReadinessPanel result={assess({ verdict: 'unknown', missing_materials: [], questions: [], blocking: [], warnings: [warning] })} />)

    expect(screen.getByTestId('readiness-verdict').textContent).toBe('判断没跑成功')
    expect(screen.getByText('没跑成功的原因')).toBeTruthy()
    expect(screen.getByText(`· ${warning}`)).toBeTruthy()
  })
})

describe('ReadinessPanel：复制清单', () => {
  it('复制的是纯文本标题 + 分组 + 条目（含向谁要 / 形式 / 问题）', async () => {
    render(<ReadinessPanel result={assess()} />)

    fireEvent.click(screen.getByTestId('readiness-copy'))

    await waitFor(() => expect(copyTextMock).toHaveBeenCalledTimes(1))
    const text = copyTextMock.mock.calls[0]?.[0] ?? ''

    expect(text).toContain('立案前判断：现在还不能出，缺 1 项')
    expect(text).toContain('【必须补】')
    expect(text).toContain('- 被告身份证复印件或户籍信息：立案需明确被告并送达（向委托人 / 律师调查要 · 形式：复印件 / 公安查询单）')
    expect(text).toContain('【影响金额】')
    expect(text).toContain('- 欠款对账与银行流水：影响欠款金额认定（向委托人要 · 形式：银行流水）')
    expect(text).toContain('【影响胜诉】')
    expect(text).toContain('【要核实的问题】')
    expect(text).toContain('- 2026 年 6 月的管理维护费是否已缴？（问委托人经办人 · 律师函只列 7-12 月）')
    // 纯文本：不带 markdown / HTML 标记
    expect(text).not.toContain('<')
    await waitFor(() => expect(vi.mocked(toast.success)).toHaveBeenCalledWith('已复制材料清单'))
  })

  it('复制失败如实报错，不假装成功', async () => {
    copyTextMock.mockResolvedValue(false)
    render(<ReadinessPanel result={assess()} />)

    fireEvent.click(screen.getByTestId('readiness-copy'))

    await waitFor(() => expect(vi.mocked(toast.error)).toHaveBeenCalled())
    expect(vi.mocked(toast.success)).not.toHaveBeenCalled()
  })
})
