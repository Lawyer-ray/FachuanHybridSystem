// @vitest-environment jsdom
/**
 * 红字发票 · 冲红重开卡（jsdom）。
 *
 * 这张卡是红票唯一的处理入口，三条纪律必须被钉住：
 * - 三段（原票 / 红票 / 新票）必须一起出现，否则人看不出「这是一件事」；
 * - 主按钮禁用条件与 `canConfirmRedReenact` 完全一致——金额未知时冲红会让账少
 *   一笔负数，所以禁用时必须给出「重解析」这个正解，而不是只说不能点；
 * - 「仅冲红」是破坏性操作，必须过二次确认，且取消不能触发请求。
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { RedReenactCard } from './RedReenactCard'
import type { InvoiceIntake, RedGroup } from '../types'

afterEach(cleanup)

function item(over: Partial<RedGroup['red']> = {}): RedGroup['red'] {
  return { intake_id: 2, invoice_id: null, invoice_number: '264420000102001', total_amount: '-40000.00', ...over }
}

function group(over: Partial<RedGroup> = {}): RedGroup {
  return {
    group_key: 'g-1',
    original: item({ intake_id: null, invoice_id: 88, invoice_number: '264420000368336', total_amount: '40000.00' }),
    red: item(),
    reissue: item({ intake_id: 3, invoice_number: '264420000185941', total_amount: '40000.00' }),
    ...over,
  }
}

function redIntake(over: Partial<InvoiceIntake> = {}): InvoiceIntake {
  return {
    id: 2,
    invoice_number: '264420000102001',
    invoice_date: '2026-11-10',
    total_amount: '-40000.00',
    buyer_name: '某客户',
    project_code: '',
    remark: '',
    status: 'pending',
    status_label: '待确认',
    suggested_contract_id: 160,
    suggested_contract_name: '陈某非诉专项（关厂、清盘）',
    suggested_payment_id: null,
    payment_pick_confidence: 'red_offset',
    payment_pick_note: '',
    payment_options: [],
    confirmed_contract_id: null,
    confirmed_contract_name: null,
    confirmed_payment_id: null,
    invoice_id: null,
    invoice_display_filename: '',
    invoice_folder_subpath: '',
    candidates: [],
    excluded_hints: [],
    inbox_message_id: 10,
    subject: '',
    sender: '',
    is_red: true,
    red_against_number: '264420000368336',
    red_confirmation_no: '',
    offset_invoice: null,
    supersedes_intake_id: null,
    superseded_by_intake_id: null,
    reatch_group: null,
    ...over,
  }
}

const noop = () => {}

function renderCard({
  g = group(),
  red = redIntake(),
  onReenact = noop,
  onConfirmOnly = noop,
  onReparse = noop,
  onDetail = noop,
  busy = false,
}: {
  g?: RedGroup
  red?: InvoiceIntake
  onReenact?: () => void
  onConfirmOnly?: () => void
  onReparse?: () => void
  onDetail?: () => void
  busy?: boolean
} = {}) {
  return render(
    <RedReenactCard
      group={g}
      red={red}
      busy={busy}
      onConfirmReenact={onReenact}
      onConfirmOnly={onConfirmOnly}
      onReparse={onReparse}
      onDetail={onDetail}
    />,
  )
}

describe('RedReenactCard', () => {
  it('红票标识 + 项目名 + 三段票号与金额', () => {
    renderCard()
    expect(screen.getByText('红字发票')).toBeTruthy()
    expect(screen.getByText('陈某非诉专项（关厂、清盘）')).toBeTruthy()
    // 原票 / 红票 / 新票三段的尾号与金额
    expect(screen.getByText('…368336')).toBeTruthy()
    expect(screen.getByText('…102001')).toBeTruthy()
    expect(screen.getByText('…185941')).toBeTruthy()
    expect(screen.getAllByText('¥40,000.00')).toHaveLength(2)
    // 红票金额保留负号
    expect(screen.getByText('¥-40,000.00')).toBeTruthy()
  })

  it('给出后果说明：冲红后原票作废、新票替代原票入账', () => {
    renderCard()
    expect(screen.getByText('冲红后原票作废，新票替代原票入账')).toBeTruthy()
  })

  it('条件齐备：主按钮可点，点击直接整组提交（不开二次确认）', () => {
    const onReenact = vi.fn()
    renderCard({ onReenact })
    const btn = screen.getByRole('button', { name: /冲红并确认重开/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(false)
    fireEvent.click(btn)
    expect(onReenact).toHaveBeenCalledTimes(1)
  })

  it('红票金额未识别：主按钮禁用 + 说明原因 + 给「重解析」入口', () => {
    const onReparse = vi.fn()
    const red = redIntake({ total_amount: null })
    renderCard({ g: group({ red: item({ total_amount: null }) }), red, onReparse })

    const btn = screen.getByRole('button', { name: /冲红并确认重开/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.title).toContain('请先重解析这张红票')
    expect(screen.getByText('红票金额未识别')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: /重解析/ }))
    expect(onReparse).toHaveBeenCalledTimes(1)
  })

  it('原票不在库：主按钮禁用并明说需人工处理，不给重解析（重解析解决不了原票缺失）', () => {
    renderCard({ g: group({ original: null }) })
    const btn = screen.getByRole('button', { name: /冲红并确认重开/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(screen.getByText('原票不在系统里，需人工处理')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /重解析/ })).toBeNull()
  })

  it('没有重开的新票：主按钮禁用且新票段给出占位', () => {
    renderCard({ g: group({ reissue: null }) })
    expect((screen.getByRole('button', { name: /冲红并确认重开/ }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText('未挑到新票')).toBeTruthy()
  })

  it('「仅冲红」需二次确认：取消不发请求，确认才发一次', () => {
    const onConfirmOnly = vi.fn()
    renderCard({ onConfirmOnly })

    fireEvent.click(screen.getByRole('button', { name: '仅冲红' }))
    expect(screen.getByText('只冲红、不重开？')).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(onConfirmOnly).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: '仅冲红' }))
    fireEvent.click(screen.getByRole('button', { name: '确认仅冲红' }))
    expect(onConfirmOnly).toHaveBeenCalledTimes(1)
  })

  it('busy 时主按钮与仅冲红都禁用，详情仍可点', () => {
    const onDetail = vi.fn()
    renderCard({ busy: true, onDetail })
    expect((screen.getByRole('button', { name: /冲红并确认重开/ }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: '仅冲红' }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: '详情' }))
    expect(onDetail).toHaveBeenCalledTimes(1)
  })
})
