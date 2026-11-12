// @vitest-environment jsdom
/**
 * 待认领发票卡的分组渲染（jsdom）。
 *
 * 钉住三件事：
 * - 同一组的红票 + 新票聚成一张 `RedReenactCard`，不再各占一行；
 * - 角标按「件事」算（standalone 行数 + 组数），不是原始 intake 条数；
 * - 失败态与空态文案互相不串（「失败 ≠ 空」的既有纪律）。
 *
 * mock 边界：只桩同域的 `../api`（查询与三个红票动作用的端点）与 `sonner`。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const stubs = vi.hoisted(() => ({
  listPendingInvoices: vi.fn(),
  confirmInvoiceIntake: vi.fn(),
  confirmRedReenact: vi.fn(),
  confirmRedOnly: vi.fn(),
  reparseIntake: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

vi.mock('../api', () => ({
  INVOICE_INTAKE_PENDING_KEY: ['invoice-intake-pending'],
  INVOICE_INTAKE_COUNT_KEY: ['invoice-intake-count'],
  INVOICE_SELECTABLE_KEY: ['invoice-intake-selectable'],
  listSelectableContracts: vi.fn().mockResolvedValue([]),
  getInvoiceIntake: vi.fn(),
  copyInvoiceToClipboard: vi.fn(),
  listPendingInvoices: stubs.listPendingInvoices,
  getPendingInvoiceCount: vi.fn(),
  confirmInvoiceIntake: stubs.confirmInvoiceIntake,
  confirmRedReenact: stubs.confirmRedReenact,
  confirmRedOnly: stubs.confirmRedOnly,
  reparseIntake: stubs.reparseIntake,
  rejectInvoiceIntake: vi.fn(),
  reopenInvoiceIntake: vi.fn(),
}))
vi.mock('sonner', () => ({ toast: stubs.toast }))

import { PendingInvoicesCard } from './PendingInvoicesCard'
import type { InvoiceIntake, RedGroup } from '../types'

/** react-router 的 useNavigate（详情弹窗会引用，这里不展开渲染它） */
vi.mock('react-router', () => ({ useNavigate: () => vi.fn() }))

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

const RED = intake({
  id: 2,
  invoice_number: '264420000102001',
  total_amount: '-40000.00',
  is_red: true,
  red_against_number: '264420000368336',
  reatch_group: group(),
})
const REISSUE = intake({ id: 3, invoice_number: '264420000185941', reatch_group: group() })
const PLAIN = intake({ id: 5 })

function renderCard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } })
  return render(
    <QueryClientProvider client={client}>
      <PendingInvoicesCard />
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(cleanup)

describe('PendingInvoicesCard 分组', () => {
  it('同组红票 + 新票聚成一张冲红重开卡，角标按「件事」计', async () => {
    stubs.listPendingInvoices.mockResolvedValue([RED, REISSUE, PLAIN])
    renderCard()

    // 组卡出现**一次**（两条 intake → 一张卡），且三段齐备
    expect(await screen.findByText('冲红后原票作废，新票替代原票入账')).toBeTruthy()
    expect(screen.getAllByRole('button', { name: /冲红并确认重开/ })).toHaveLength(1)
    expect(screen.getByText('…185941')).toBeTruthy()
    // 单行仍在（普通票走 InvoiceIntakeRow）
    expect(screen.getByText('系统建议：张某与某公司合同纠纷')).toBeTruthy()
    // 3 条 intake → 2 件事
    expect(screen.getByText('2 件')).toBeTruthy()
  })

  it('只有一组冲红重开时角标为 1（不是 2 条原始记录）', async () => {
    stubs.listPendingInvoices.mockResolvedValue([RED, REISSUE])
    renderCard()
    expect(await screen.findByText('1 件')).toBeTruthy()
  })

  it('空列表：空态文案出现，不渲染任何组卡', async () => {
    stubs.listPendingInvoices.mockResolvedValue([])
    renderCard()
    expect(await screen.findByText('暂无待认领发票')).toBeTruthy()
    expect(screen.queryByRole('button', { name: /冲红并确认重开/ })).toBeNull()
  })

  it('加载失败：失败文案与重试入口出现，不复用空态文案', async () => {
    // 错误对象不带 message：errMessage 才会退回调用方给的 fallback 文案，
    // 这里要看的正是「失败」与「空」不是同一件事
    stubs.listPendingInvoices.mockRejectedValue({})
    renderCard()
    expect(await screen.findByText(/待认领发票加载失败/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy()
    expect(screen.queryByText('暂无待认领发票')).toBeNull()
  })
})
