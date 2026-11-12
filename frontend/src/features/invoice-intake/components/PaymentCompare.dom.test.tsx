// @vitest-environment jsdom
/**
 * PaymentCompare 判定测试（jsdom）。
 *
 * 这是发票详情里**唯一有决策价值**的一段：不只并排两个数字，而是直接给判定。
 * 每条分支都必须给出可执行的下一步，不能只说「不相等」：
 * - 相等 → 金额吻合；
 * - 发票多 → 说明按收款上限封顶、差额另处理；
 * - 发票少 → 说明可能是部分开票；
 * - 有一方识别不出 → 建议核对原件（而不是编一个差额）。
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { PaymentCompare } from './PaymentCompare'
import type { InvoiceIntake, InvoicePaymentOption } from '../types'

function option(over: Partial<InvoicePaymentOption> = {}): InvoicePaymentOption {
  return { id: 7, amount: '2400.00', received_at: '2026-11-01', note: '', ...over }
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
    suggested_payment_id: 7,
    payment_pick_confidence: 'exact',
    payment_pick_note: '',
    payment_options: [option()],
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

describe('PaymentCompare', () => {
  it('金额相等：绿勾「金额吻合」，不出现差额警示', () => {
    render(<PaymentCompare intake={intake()} />)
    expect(screen.getByText('金额吻合')).toBeTruthy()
    expect(screen.queryByText(/发票比收款/)).toBeNull()
  })

  it('容差内的浮点差异仍算吻合', () => {
    render(<PaymentCompare intake={intake({ total_amount: '2400.004' })} />)
    expect(screen.getByText('金额吻合')).toBeTruthy()
  })

  it('发票比收款多：给出差额并说明按收款上限封顶', () => {
    render(<PaymentCompare intake={intake({ total_amount: '2800.00' })} />)
    expect(screen.getByText('金额不符')).toBeTruthy()
    expect(screen.getByText(/发票比收款多 ¥400\.00/)).toBeTruthy()
    expect(screen.getByText(/按收款上限封顶/)).toBeTruthy()
  })

  it('发票比收款少：说明可能是部分开票', () => {
    render(<PaymentCompare intake={intake({ total_amount: '2000.00' })} />)
    expect(screen.getByText(/发票比收款少 ¥400\.00/)).toBeTruthy()
    expect(screen.getByText(/部分开票/)).toBeTruthy()
  })

  it('容错千分位与 ¥ / 空格（后端格式不统一也不误判）', () => {
    render(<PaymentCompare intake={intake({ total_amount: '¥ 2,400.00', payment_options: [option({ amount: '2400' })] })} />)
    expect(screen.getByText('金额吻合')).toBeTruthy()
  })

  it('一方金额识别不出：给「建议核对原件」，不编差额', () => {
    render(<PaymentCompare intake={intake({ total_amount: null, payment_options: [option({ amount: '' })] })} />)
    expect(screen.getByText(/有一方未能识别，建议先核对原件/)).toBeTruthy()
  })

  it('已确认且指定了收款：直接说「已挂到收款 #N」', () => {
    render(<PaymentCompare intake={intake({ status: 'confirmed', confirmed_payment_id: 9 })} />)
    expect(screen.getByText('已挂到收款 #9')).toBeTruthy()
  })

  it('已确认但未指定收款：说明挂在项目名下', () => {
    render(<PaymentCompare intake={intake({ status: 'confirmed', confirmed_payment_id: null })} />)
    expect(screen.getByText('已挂到项目名下（未指定收款）')).toBeTruthy()
  })

  it('无候选收款（payment_options 缺失也不崩）：说明「先开票后付款」', () => {
    const row = intake({ payment_options: undefined as unknown as InvoicePaymentOption[], suggested_payment_id: null, payment_pick_confidence: 'no_payment' })
    render(<PaymentCompare intake={row} />)
    expect(screen.getByText(/该项目暂无收款记录/)).toBeTruthy()
  })

  it('多笔收款且无法判定：明确说「系统不替你猜」并给出笔数', () => {
    const row = intake({
      payment_options: [option({ id: 1 }), option({ id: 2, amount: '1000.00' })],
      suggested_payment_id: null,
      payment_pick_confidence: 'ambiguous',
    })
    render(<PaymentCompare intake={row} />)
    expect(screen.getByText(/该项目有 2 笔收款，系统不替你猜是哪一笔/)).toBeTruthy()
  })

  it('amount_mismatch 档：复合的「金额不符」徽标与置信度说明各自成立', () => {
    const row = intake({ payment_pick_confidence: 'amount_mismatch', total_amount: '2800.00' })
    render(<PaymentCompare intake={row} />)
    expect(screen.getByText('金额不符')).toBeTruthy()
    expect(screen.getByText('金额与收款不符')).toBeTruthy()
  })

  it('非 exact 的置信度会附带说明文案（ambiguous 档）', () => {
    const row = intake({
      payment_options: [option(), option({ id: 8, amount: '100.00' })],
      suggested_payment_id: 7,
      payment_pick_confidence: 'ambiguous',
    })
    render(<PaymentCompare intake={row} />)
    expect(screen.getByText('多笔收款，请自选')).toBeTruthy()
  })

  it('exact 置信度不重复说明（已由「金额吻合」表达）', () => {
    render(<PaymentCompare intake={intake()} />)
    expect(screen.queryByText('已预选收款')).toBeNull()
  })

  it('收款有备注时展示在到账行', () => {
    render(<PaymentCompare intake={intake({ payment_options: [option({ note: '尾款' })] })} />)
    expect(screen.getByText('到账 2026-11-01 · 尾款')).toBeTruthy()
  })
})
