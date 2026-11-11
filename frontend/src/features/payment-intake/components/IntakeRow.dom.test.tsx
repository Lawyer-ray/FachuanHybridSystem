// @vitest-environment jsdom
/**
 * payment-intake IntakeRow 展示与禁用态（jsdom）。
 *
 * 侧栏很窄，一行只讲四件事：多少钱、谁付的、建议哪个项目、能不能确认。
 * 契约重点：
 * - 没有可信建议时「确认」必须禁用（不能让人一键确认猜测）；
 * - 只有金额吻合时单独染黄警示（这是最容易错的一档）；
 * - 被排除的线索要展示原因，否则用户看不懂「为什么匹配不上」。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { IntakeRow } from './IntakeRow'
import type { Intake, IntakeCandidate } from '../types'

function candidate(over: Partial<IntakeCandidate> = {}): IntakeCandidate {
  return {
    contract_id: 160,
    contract_name: '张某与某公司合同纠纷',
    kind: 'exact',
    score: 1,
    reasons: ['付款人 = 委托人'],
    outstanding_amount: '10000.00',
    fee_mode: 'fixed',
    caveat: '',
    ...over,
  }
}

function intake(over: Partial<Intake> = {}): Intake {
  return {
    id: 1,
    amount: '5000.00',
    received_at: '2026-11-04',
    payer_name: '张三',
    on_behalf_of: '',
    display_payer: '张三',
    status: 'pending',
    status_label: '待确认',
    bank_remark: '',
    suggested_contract_id: 160,
    suggested_contract_name: '张某与某公司合同纠纷',
    confirmed_contract_id: null,
    confirmed_contract_name: null,
    payment_id: null,
    decision_note: '',
    candidates: [candidate()],
    excluded_hints: [],
    inbox_message_id: 10,
    subject: '',
    sender: '',
    ...over,
  }
}

const noop = () => {}

describe('payment-intake IntakeRow', () => {
  it('展示金额、到账日期、付款人与类别徽标', () => {
    render(<IntakeRow intake={intake()} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText('¥5,000.00')).toBeTruthy()
    expect(screen.getByText('2026-11-04')).toBeTruthy()
    expect(screen.getByText('张三')).toBeTruthy()
    expect(screen.getByText('高度匹配')).toBeTruthy()
  })

  it('有实名命中：结论带项目名，确认按钮可点', () => {
    render(<IntakeRow intake={intake()} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText('高度匹配：张某与某公司合同纠纷')).toBeTruthy()
    expect((screen.getByRole('button', { name: /确认/ }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('只有金额吻合：强提醒「请核对后选择」，且不展示类别徽标以外的绿色结论', () => {
    const row = intake({ candidates: [candidate({ kind: 'amount_only' })] })
    render(<IntakeRow intake={row} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText('仅有金额吻合，请核对后选择')).toBeTruthy()
    expect(screen.getByText('仅金额吻合')).toBeTruthy()
  })

  it('无候选：结论为「未匹配到在办项目」，确认按钮禁用', () => {
    const row = intake({ candidates: [], suggested_contract_id: null, suggested_contract_name: null })
    render(<IntakeRow intake={row} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText('未匹配到在办项目，请手动选择')).toBeTruthy()
    expect((screen.getByRole('button', { name: /确认/ }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('busy 时确认与「换个项目」都禁用（防重复提交）', () => {
    render(<IntakeRow intake={intake()} busy onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect((screen.getByRole('button', { name: /确认/ }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: /换个项目/ }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('展示候选理由第一行（解释系统为什么这么想）', () => {
    render(<IntakeRow intake={intake()} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText('付款人 = 委托人')).toBeTruthy()
  })

  it('候选无理由时不渲染理由行', () => {
    const row = intake({ candidates: [candidate({ reasons: [] })] })
    render(<IntakeRow intake={row} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.queryByText('付款人 = 委托人')).toBeNull()
  })

  it('被排除的线索展示「项目名：原因」，这是解释匹配失败的钥匙', () => {
    const row = intake({
      excluded_hints: [{ contract_id: 9, contract_name: '已收满项目', excluded_by: 'fully_paid', note: '费用已收齐' }],
    })
    render(<IntakeRow intake={row} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText(/已收满项目：费用已收齐/)).toBeTruthy()
  })

  it('三个动作各自回传回调', () => {
    const onConfirm = vi.fn()
    const onChange = vi.fn()
    const onDetail = vi.fn()
    render(<IntakeRow intake={intake()} busy={false} onConfirm={onConfirm} onChange={onChange} onDetail={onDetail} />)

    fireEvent.click(screen.getByRole('button', { name: /确认/ }))
    fireEvent.click(screen.getByRole('button', { name: /换个项目/ }))
    fireEvent.click(screen.getByRole('button', { name: '详情' }))

    expect(onConfirm).toHaveBeenCalledTimes(1)
    expect(onChange).toHaveBeenCalledTimes(1)
    expect(onDetail).toHaveBeenCalledTimes(1)
  })
})
