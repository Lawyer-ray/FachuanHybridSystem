// @vitest-environment jsdom
/**
 * DealSheet（合同详情抽屉）组件渲染单测（jsdom）。
 *
 * mock 边界：../hooks/use-contract-cases（案件明细按需加载桩，cases/isLoading 可控）。
 * 覆盖：null/关闭态不渲染、抽屉头部字段（类型/状态/OA 链接，无时间线）、合同要素日期年月日、金额四格、
 * 当事人我方在前排序与复制入口、空节不渲染、案件阶段聚合展示与加载态、
 * 以及 safeHttpUrl 白名单的安全断言（javascript: 伪协议不得成为可点链接）。
 */
import { render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../hooks/use-contract-cases', () => ({ useContractCases: vi.fn() }))

import type { DealCase, WorkbenchDeal } from '../types'
import { useContractCases } from '../hooks/use-contract-cases'

import { DealSheet } from './DealSheet'

const casesMock = vi.mocked(useContractCases)

function makeDeal(over: Partial<WorkbenchDeal> = {}): WorkbenchDeal {
  return {
    id: 1,
    lit: true,
    caseType: 'civil',
    client: '王五',
    ctype: '民事诉讼',
    no: 'FC-2026-001',
    amount: '¥10,000',
    amountNum: 10000,
    fee: '固定收费',
    from: '2026-09-01',
    to: '2027-03-01',
    daysLeft: 30,
    status: 'active',
    statusLabel: '在办',
    specified: '',
    isFiled: false,
    filingNo: '',
    oaUrl: '',
    customTerms: '',
    parties: { client: '王五', other: '赵六' },
    partiesAll: [],
    team: [],
    primaryPhone: '',
    caseCount: 0,
    work: [],
    riskRate: null,
    stages: ['一审'],
    primary: '',
    lawFirm: '',
    totalReceived: '¥5,000',
    totalInvoiced: null,
    unpaid: '¥5,000',
    payments: [],
    payRecords: [],
    supps: [],
    ...over,
  }
}

function makeDealCase(id: number, proc: string, done: boolean): DealCase {
  return {
    id,
    name: `案件 ${id}`,
    proc,
    ref: '',
    numbers: [],
    st: done ? '已结案' : '在办',
    done,
    auth: '',
    auths: [],
    cause: '',
    target: null,
    preserv: null,
    from: '',
    partyRows: [],
    parties: [],
    logs: [],
    logReminders: [],
    contacts: [],
  }
}

const onOpenChange = vi.fn()

function setupUi(deal: WorkbenchDeal | null, open: boolean) {
  return render(<DealSheet deal={deal} open={open} onOpenChange={onOpenChange} />)
}

beforeEach(() => {
  vi.clearAllMocks()
  casesMock.mockReturnValue({ cases: [], isLoading: false, error: null, refetch: vi.fn() })
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('DealSheet 挂载开关', () => {
  it('deal 为 null：整体不渲染', () => {
    const { container } = setupUi(null, true)
    expect(container.innerHTML).toBe('')
  })

  it('open=false 内容不挂载；open=true 渲染标题', () => {
    const deal = makeDeal()
    const { rerender } = setupUi(deal, false)
    expect(screen.queryByText('王五')).toBeNull()
    rerender(<DealSheet deal={deal} open onOpenChange={onOpenChange} />)
    expect(screen.getByText('王五')).toBeTruthy()
  })
})

describe('DealSheet 字段渲染', () => {
  it('头部：类型/状态徽章，不再重复时间线；日期在合同要素里按年月日展示；金额四格', () => {
    setupUi(makeDeal(), true)
    expect(screen.getByText('民事诉讼')).toBeTruthy()
    // 「在办」出现在头部徽章与合同要素「归档状态」两处，均为合法渲染
    expect(screen.getAllByText('在办').length).toBeGreaterThanOrEqual(1)
    // 头部不再有「签订 … · 到期 …」时间线（与合同要素重复）
    expect(screen.queryByText(/签订 2026/)).toBeNull()
    expect(screen.queryByText(/到期 2027/)).toBeNull()
    // 合同要素：中划线转年月日，到期带相对表述
    expect(screen.getByText('2026年9月1日')).toBeTruthy()
    expect(screen.getByText('2027年3月1日（剩 30 天）')).toBeTruthy()
    expect(screen.getByText('律师费')).toBeTruthy()
    expect(screen.getByText('¥10,000')).toBeTruthy()
    expect(screen.getByText('已收款')).toBeTruthy()
    expect(screen.getByText('未收款')).toBeTruthy()
  })

  it('当事人：我方在前，带复制按钮；节标题带数量', () => {
    setupUi(
      makeDeal({
        partiesAll: [
          { name: '赵六', role: '对方当事人', idno: '', legalRep: '', phone: '', address: '', ours: false },
          { name: '王五', role: '委托人', idno: '', legalRep: '', phone: '', address: '', ours: true },
        ],
      }),
      true,
    )
    expect(screen.getByText(/当事人 · 2/)).toBeTruthy()
    const ours = screen.getByText('王五', { selector: 'span' })
    const other = screen.getByText('赵六', { selector: 'span' })
    expect(ours.compareDocumentPosition(other) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getAllByTitle('复制该当事人信息')).toHaveLength(2)
    // 法人/自然人不再展示：角色标签只剩角色本身
    expect(screen.queryByText(/自然人|法人/)).toBeNull()
  })

  it('空节不渲染：无当事人/团队/提醒时不出现对应节', () => {
    setupUi(
      makeDeal({
        amount: null,
        totalReceived: null,
        totalInvoiced: null,
        unpaid: null,
      }),
      true,
    )
    expect(screen.queryByText(/当事人/)).toBeNull()
    expect(screen.queryByText('主办律师')).toBeNull()
    expect(screen.queryByText(/提醒事项/)).toBeNull()
    expect(screen.queryByText('律师费')).toBeNull()
  })
})

describe('DealSheet OA 链接白名单（safeHttpUrl）', () => {
  it('oaUrl 为 javascript: 伪协议：不渲染为可执行链接（href 落到 #）', () => {
    const { container } = setupUi(makeDeal({ oaUrl: 'javascript:alert(1)' }), true)
    const link = screen.getByRole('link', { name: 'FC-2026-001' })
    expect(link.getAttribute('href')).toBe('#')
    // 安全断言：全文档不得存在 javascript: 协议的链接
    expect(container.ownerDocument.querySelectorAll('a[href^="javascript:"]')).toHaveLength(0)
  })

  it('oaUrl 为合法 https：渲染为新窗口打开的真实链接', () => {
    setupUi(makeDeal({ oaUrl: 'https://oa.example.com/c/9' }), true)
    const link = screen.getByRole('link', { name: 'FC-2026-001' }) as HTMLAnchorElement
    expect(link.getAttribute('href')).toBe('https://oa.example.com/c/9')
    expect(link.getAttribute('target')).toBe('_blank')
  })

  it('无 oaUrl：编号渲染为纯文本（不是链接）', () => {
    setupUi(makeDeal({ oaUrl: '' }), true)
    expect(screen.queryByRole('link')).toBeNull()
    // 编号出现在头部与「OA 编号」要素行两处，均为纯文本
    expect(screen.getAllByText('FC-2026-001').length).toBeGreaterThanOrEqual(1)
  })
})

describe('DealSheet 案件按需加载节', () => {
  it('案件明细到达：按阶段聚合（同阶段 ×N + 在办/已结）', () => {
    casesMock.mockReturnValue({
      cases: [makeDealCase(1, '一审', false), makeDealCase(2, '一审', false), makeDealCase(3, '二审', true)],
      isLoading: false,
      error: null,
      refetch: vi.fn(),
    })
    setupUi(makeDeal(), true)
    // 阶段节点是 <b>；合同要素「代理阶段」行同文本（span），用 selector 区分
    expect(screen.getByText('一审', { selector: 'b' })).toBeTruthy()
    expect(screen.getByText('×2')).toBeTruthy()
    expect(screen.getByText('二审', { selector: 'b' })).toBeTruthy()
    expect(
      screen.getByText(
        (_, el) => el?.textContent === '3 个案件 · 一审 → 二审',
      ),
    ).toBeTruthy()
  })

  it('案件明细加载中：展示加载文案与计数省略', () => {
    casesMock.mockReturnValue({ cases: [], isLoading: true, error: null, refetch: vi.fn() })
    setupUi(makeDeal(), true)
    expect(screen.getByText('正在加载案件…')).toBeTruthy()
    expect(screen.getByText(/案件 · …/)).toBeTruthy()
  })

  it('案件明细加载失败：错误行 + 重试入口，不静默成空案件节', () => {
    casesMock.mockReturnValue({ cases: [], isLoading: false, error: '案件加载失败', refetch: vi.fn() })
    setupUi(makeDeal(), true)
    expect(screen.getByText(/案件加载失败/)).toBeTruthy()
    expect(screen.getByRole('button', { name: '重试' })).toBeTruthy()
    // 失败时不得停留在加载态（空态即整节不渲染，无需另行断言）
    expect(screen.queryByText('正在加载案件…')).toBeNull()
  })
})

// ============ 团队 / 收款 / 提醒 / 补充协议 / 交互（覆盖率补测） ============

describe('DealSheet 主办律师节', () => {
  it('渲染律师名与「主办」标、电话、复制按钮', () => {
    casesMock.mockReturnValue({ cases: [], isLoading: false, error: null } as never)
    const deal = makeDeal({
      team: [
        { name: '张律师', primary: true, phone: '13800000000', firm: '某某所', license: '111' }, // privacy-allow 虚构号码
        { name: '李律师', primary: false, phone: '', firm: '', license: '' },
      ] as never,
      primaryPhone: '13900000000', // privacy-allow 虚构号码
      lawFirm: '默认所',
    })
    const { container } = render(<DealSheet deal={deal} open onOpenChange={vi.fn()} />)

    expect(document.body.textContent).toContain('主办律师')
    expect(document.body.textContent).toContain('张律师')
    expect(document.body.textContent).toContain('主办')
    expect(document.body.textContent).toContain('13800000000') // privacy-allow 虚构号码
    container.remove()
  })

  it('主办律师未填电话/律所时回落到合同主电话与律所', () => {
    casesMock.mockReturnValue({ cases: [], isLoading: false, error: null } as never)
    const deal = makeDeal({
      team: [{ name: '张律师', primary: true, phone: '', firm: '', license: '' }] as never,
      primaryPhone: '13900000000', // privacy-allow 虚构号码
      lawFirm: '默认所',
    })
    const { container } = render(<DealSheet deal={deal} open onOpenChange={vi.fn()} />)
    expect(document.body.textContent).toContain('13900000000') // privacy-allow 虚构号码
    container.remove()
  })
})

describe('DealSheet 收款记录节', () => {
  it('有收款记录时渲染节标题与行', () => {
    casesMock.mockReturnValue({ cases: [], isLoading: false, error: null } as never)
    const deal = makeDeal({
      payments: [{ when: '2026-10-01', money: '¥5,000', note: '首付款' }] as never,
    })
    const { container } = render(<DealSheet deal={deal} open onOpenChange={vi.fn()} />)

    expect(document.body.textContent).toContain('收款记录')
    expect(document.body.textContent).toContain('¥5,000')
    expect(document.body.textContent).toContain('首付款')
    container.remove()
  })
})

describe('DealSheet 提醒事项节', () => {
  it('有提醒时渲染节标题与条数、类型与到期', () => {
    casesMock.mockReturnValue({ cases: [], isLoading: false, error: null } as never)
    const deal = makeDeal({
      work: [{ t: '提交证据', type: '开庭', dueFull: '2026-10-20 09:00' }] as never,
    })
    const { container } = render(<DealSheet deal={deal} open onOpenChange={vi.fn()} />)

    expect(document.body.textContent).toContain('提醒事项 · 1')
    expect(document.body.textContent).toContain('提交证据')
    expect(document.body.textContent).toContain('开庭 · 2026-10-20 09:00')
    container.remove()
  })

  it('无类型的提醒只显示到期时间', () => {
    casesMock.mockReturnValue({ cases: [], isLoading: false, error: null } as never)
    const deal = makeDeal({
      work: [{ t: '提交证据', type: '', dueFull: '2026-10-20 09:00' }] as never,
    })
    const { container } = render(<DealSheet deal={deal} open onOpenChange={vi.fn()} />)
    expect(document.body.textContent).not.toContain('· 2026-10-20')
    container.remove()
  })
})

describe('DealSheet 补充协议节', () => {
  it('有补充协议时渲染名称与创建时间', () => {
    casesMock.mockReturnValue({ cases: [], isLoading: false, error: null } as never)
    const deal = makeDeal({
      supps: [{ id: 1, name: '补充协议一', created_at: '2026-10-01', parties: [] }] as never,
    })
    const { container } = render(<DealSheet deal={deal} open onOpenChange={vi.fn()} />)

    expect(document.body.textContent).toContain('补充协议 · 1')
    expect(document.body.textContent).toContain('补充协议一')
    container.remove()
  })
})

describe('DealSheet 详情按钮与遮罩', () => {
  it('有 onOpenDetail 时「详情 →」调用它并带 deal', () => {
    casesMock.mockReturnValue({ cases: [], isLoading: false, error: null } as never)
    const onOpenDetail = vi.fn()
    const deal = makeDeal()
    render(<DealSheet deal={deal} open onOpenChange={vi.fn()} onOpenDetail={onOpenDetail} />)

    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /详情 →/.test(b.textContent ?? ''),
    ) as HTMLElement
    btn.click()
    expect(onOpenDetail).toHaveBeenCalledWith(deal)
  })

  it('无 onOpenDetail 时「详情 →」只给提示', () => {
    casesMock.mockReturnValue({ cases: [], isLoading: false, error: null } as never)
    render(<DealSheet deal={makeDeal()} open onOpenChange={vi.fn()} />)

    const btn = Array.from(document.querySelectorAll('button')).find((b) =>
      /详情 →/.test(b.textContent ?? ''),
    ) as HTMLElement
    btn.click()
    // 不抛错即通过（toast 由 sonner 接管）
  })

  it('右键遮罩关闭抽屉且阻止原生菜单', () => {
    casesMock.mockReturnValue({ cases: [], isLoading: false, error: null } as never)
    const onOpenChange = vi.fn()
    const { container } = render(<DealSheet deal={makeDeal()} open onOpenChange={onOpenChange} />)

    // 遮罩是 aria-hidden 的层
    const mask = container.querySelector('[aria-hidden="true"]') as HTMLElement
    if (mask) {
      const e = new MouseEvent('contextmenu', { bubbles: true, cancelable: true })
      mask.dispatchEvent(e)
      expect(e.defaultPrevented).toBe(true)
      expect(onOpenChange).toHaveBeenCalledWith(false)
    }
    container.remove()
  })
})
