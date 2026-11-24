// @vitest-environment jsdom
/**
 * DateCandidateList 测试（jsdom）。
 *
 * 候选确认要可解释：每条三行（时间/类型 + 原文摘录 + 推导依据），
 * 复核标记走黄色徽标（最多 2 个，其余折叠 +N，全量放 title）。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import type { CandidateRow } from '../domain'

import { DateCandidateList } from './DateCandidateList'

function makeRow(over: Partial<CandidateRow> = {}): CandidateRow {
  return {
    key: 'c-1',
    candidateId: 1,
    checked: true,
    dueLocal: '2026-11-30T09:00',
    reminderType: 'evidence_deadline',
    label: '举证到期日',
    contextText: '请在送达之日起七日内提交证据',
    content: '',
    source: 'llm',
    confidence: 0.9,
    status: 'pending',
    reminderId: null,
    reviewFlags: [],
    anchorNote: '',
    derivationLabel: '',
    defaultChecked: true,
    ...over,
  }
}

const noop = vi.fn()

function renderList(row: CandidateRow) {
  return render(
    <DateCandidateList
      rows={[row]}
      interactive
      busy={false}
      onToggle={noop}
      onPatch={noop}
      onSkip={noop}
      onRevoke={noop}
    />,
  )
}

describe('DateCandidateList：三行候选与复核标记', () => {
  it('渲染时间/类型、原文摘录、推导依据三行，flag 徽标最多 2 个并折叠 +N', () => {
    const { container, unmount } = renderList(
      makeRow({
        reviewFlags: ['anchor_effective', 'low_confidence', 'far_future'],
        derivationLabel: '按送达日推算',
        anchorNote: '起算点：本份文书送达日 2026-11-24 + 7 天',
        confidence: 0.9,
      }),
    )

    // 第一行：可编辑时间 + 类型选择
    expect(screen.getByDisplayValue('2026-11-30T09:00')).toBeTruthy()
    expect((screen.getByRole('combobox') as HTMLSelectElement).value).toBe('evidence_deadline')
    // 第二行：原文摘录
    expect(screen.getByText('请在送达之日起七日内提交证据')).toBeTruthy()
    // 第三行：来源 · 起算点
    expect(screen.getByText('按送达日推算 · 起算点：本份文书送达日 2026-11-24 + 7 天')).toBeTruthy()
    // flag 徽标：前两个中文标签 + 折叠计数；低置信由 flag 驱动（confidence 0.9 不再影响）
    expect(screen.getByText('起算点待确认')).toBeTruthy()
    expect(screen.getByText('低置信')).toBeTruthy()
    expect(screen.getByText('+1')).toBeTruthy()
    // 全部 flag 在 title 上
    expect(screen.getByTitle('起算点待确认、低置信、远期日期').textContent).toContain('+1')
    expect(container.textContent).not.toContain('低置信·请核对')
    unmount()
  })
})
