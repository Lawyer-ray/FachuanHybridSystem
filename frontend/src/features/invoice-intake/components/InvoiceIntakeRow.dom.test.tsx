// @vitest-environment jsdom
/**
 * invoice-intake 行组件展示与禁用态（jsdom）。
 *
 * 行只回答四件事：多少钱、谁买的、建议哪个项目、能不能确认。要钉住的：
 * - 无建议 / 非 pending 时「确认绑定」禁用（canConfirm 的两道闸门都要生效）；
 * - 预选收款确定性里「金额与收款不符」单独染黄，其余走灰；
 * - 被排除线索按「原因在前、项目名在后」，因为项目名很长，单行截断时
 *   先丢掉的是最重要的原因（实测踩过）。
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { InvoiceIntakeRow } from './InvoiceIntakeRow'
import type { InvoiceCandidate, InvoiceIntake } from '../types'

function candidate(over: Partial<InvoiceCandidate> = {}): InvoiceCandidate {
  return {
    contract_id: 160,
    contract_name: '张某与某公司合同纠纷',
    kind: 'project_code',
    score: 1,
    reasons: ['备注栏项目号命中'],
    caveat: '',
    ...over,
  }
}

function intake(over: Partial<InvoiceIntake> = {}): InvoiceIntake {
  return {
    id: 1,
    invoice_number: '26442000012915552076',
    invoice_date: '2026-11-04',
    total_amount: '2400.00',
    buyer_name: '张三',
    project_code: '2025GZM0001', // privacy-allow 虚构样例，非真实项目号
    remark: '',
    status: 'pending',
    status_label: '待确认',
    suggested_contract_id: 160,
    suggested_contract_name: '张某与某公司合同纠纷',
    suggested_payment_id: null,
    payment_pick_confidence: null,
    payment_pick_note: '',
    payment_options: [],
    confirmed_contract_id: null,
    confirmed_contract_name: null,
    confirmed_payment_id: null,
    invoice_id: null,
    invoice_display_filename: '',
    invoice_folder_subpath: '',
    candidates: [candidate()],
    excluded_hints: [],
    inbox_message_id: 10,
    subject: '',
    sender: '',
    is_red: false,
    red_against_number: '',
    red_confirmation_no: '',
    offset_invoice: null,
    supersedes_intake_id: null,
    superseded_by_intake_id: null,
    reatch_group: null,
    ...over,
  }
}

const noop = () => {}

describe('invoice-intake InvoiceIntakeRow', () => {
  it('展示金额、开票日期、购买方与匹配信号徽标', () => {
    render(<InvoiceIntakeRow intake={intake()} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText('¥2,400.00')).toBeTruthy()
    expect(screen.getByText('2026-11-04')).toBeTruthy()
    expect(screen.getByText('张三')).toBeTruthy()
    expect(screen.getByText('确定性匹配')).toBeTruthy()
  })

  it('金额未识别 / 日期缺失给占位而不是空白', () => {
    render(
      <InvoiceIntakeRow
        intake={intake({ total_amount: null, invoice_date: null })}
        busy={false}
        onConfirm={noop}
        onChange={noop}
        onDetail={noop}
      />,
    )
    expect(screen.getByText('金额未识别')).toBeTruthy()
    expect(screen.getByText('日期未识别')).toBeTruthy()
  })

  it('购买方缺失给占位', () => {
    render(<InvoiceIntakeRow intake={intake({ buyer_name: '' })} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText('购买方未识别')).toBeTruthy()
  })

  it('有建议：结论带项目名，确认按钮可点', () => {
    render(<InvoiceIntakeRow intake={intake()} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText('确定性匹配：张某与某公司合同纠纷')).toBeTruthy()
    expect((screen.getByRole('button', { name: /确认绑定/ }) as HTMLButtonElement).disabled).toBe(false)
  })

  it('无建议：结论提示需人工选择，确认按钮禁用且 title 指路「换个项目」', () => {
    const row = intake({ suggested_contract_id: null, suggested_contract_name: null, candidates: [] })
    render(<InvoiceIntakeRow intake={row} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)

    expect(screen.getByText('无可匹配的在办项目，需人工选择')).toBeTruthy()
    const btn = screen.getByRole('button', { name: /确认绑定/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.title).toBe('系统未给出可信建议，请选「换个项目」')
  })

  it('非 pending 状态：即使有建议也不能确认（canConfirm 第二道闸门）', () => {
    render(
      <InvoiceIntakeRow intake={intake({ status: 'confirmed' })} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />,
    )
    expect((screen.getByRole('button', { name: /确认绑定/ }) as HTMLButtonElement).disabled).toBe(true)
  })

  it('金额与收款不符：该提示单独染色并带出附注', () => {
    const row = intake({ payment_pick_confidence: 'amount_mismatch', payment_pick_note: '发票比收款多 400.00' })
    render(<InvoiceIntakeRow intake={row} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText('金额与收款不符（发票比收款多 400.00）')).toBeTruthy()
  })

  it('exact 档不重复附注（预选本就是确定的，无需解释）', () => {
    const row = intake({ payment_pick_confidence: 'exact', payment_pick_note: '不该出现' })
    render(<InvoiceIntakeRow intake={row} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText('已预选收款')).toBeTruthy()
    expect(screen.queryByText(/不该出现/)).toBeNull()
  })

  it('被排除线索：原因在前、项目名在后（截断时先丢掉次要信息）', () => {
    const row = intake({
      excluded_hints: [{ contract_id: 9, contract_name: '已结案的某施工合同纠纷', excluded_by: 'case_closed', note: '案件已结案' }],
    })
    render(<InvoiceIntakeRow intake={row} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText(/案件已结案：已结案的某施工合同纠纷/)).toBeTruthy()
  })

  it('红票单独出现：不渲染「确定性匹配」徽标，改渲染红字发票标识，且确认禁用', () => {
    const row = intake({
      is_red: true,
      total_amount: '-40000.00',
      red_against_number: '264420000368336',
      offset_invoice: {
        id: 88,
        invoice_number: '264420000368336',
        total_amount: '40000.00',
        contract_id: 160,
        contract_name: '张某与某公司合同纠纷',
        folder_subpath: '合同/发票',
      },
    })
    render(<InvoiceIntakeRow intake={row} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)

    // 绿色「确定性匹配」会把红票读成「可以入账」，这是 D5 要杜绝的误读
    expect(screen.queryByText('确定性匹配')).toBeNull()
    expect(screen.getByText('红字发票')).toBeTruthy()
    // 结论行改成「冲销哪张票」
    expect(screen.getByText('冲销 …368336（¥40,000.00）')).toBeTruthy()
    // 金额保留负号
    expect(screen.getByText('¥-40,000.00')).toBeTruthy()

    const btn = screen.getByRole('button', { name: /确认绑定/ }) as HTMLButtonElement
    expect(btn.disabled).toBe(true)
    expect(btn.title).toContain('冲红并确认重开')
  })

  it('红票金额未识别：占位直说是红票，不是笼统的「金额未识别」', () => {
    const row = intake({ is_red: true, total_amount: null, red_against_number: '264420000368336', offset_invoice: null })
    render(<InvoiceIntakeRow intake={row} busy={false} onConfirm={noop} onChange={noop} onDetail={noop} />)
    expect(screen.getByText('红票金额未识别')).toBeTruthy()
    expect(screen.getByText('冲销 …368336（原票不在系统里）')).toBeTruthy()
  })

  it('busy 时两个绑定按钮都禁用，详情仍可点', () => {
    const onDetail = vi.fn()
    render(<InvoiceIntakeRow intake={intake()} busy onConfirm={noop} onChange={noop} onDetail={onDetail} />)

    expect((screen.getByRole('button', { name: /确认绑定/ }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: /换个项目/ }) as HTMLButtonElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: '详情' }))
    expect(onDetail).toHaveBeenCalledTimes(1)
  })
})
