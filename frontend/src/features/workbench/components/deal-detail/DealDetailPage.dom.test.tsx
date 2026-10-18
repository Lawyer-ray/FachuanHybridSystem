// @vitest-environment jsdom
/**
 * DealDetailPage（争议解决详情页）渲染单测（jsdom + 真实 timers）。
 *
 * mock 边界：../../api 四个接口（合同 / 律师 / 按合同案件 / 按案件提醒）。
 * 覆盖：加载态、主标题=合同名 + 页头 meta、程序链按收案日期排序 + stepper 虚节点「执行」、
 * 案件节（案号 chip / 诉讼地位行 / 日志升序）、右栏期限三源合流（今日红 + 已完成剔除）、
 * 档案沉底（当事人 / 收款）、非诉委托给开发中提示、合同加载失败给错误 + 返回、非法 id 重定向。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor, within } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../../api', () => ({
  getContract: vi.fn(),
  listLawyers: vi.fn(),
  listCasesByContract: vi.fn(),
  listRemindersByCase: vi.fn(),
}))

import { getContract, listCasesByContract, listLawyers, listRemindersByCase } from '../../api'
import type { CaseListItem, ContractListItem, LawyerListItem, ReminderOut } from '../../types'

import { DealDetailPage } from './DealDetailPage'

const getContractMock = vi.mocked(getContract)
const lawyersMock = vi.mocked(listLawyers)
const casesMock = vi.mocked(listCasesByContract)
const remindersMock = vi.mocked(listRemindersByCase)

const today = new Date()
const pad = (n: number) => ('0' + n).slice(-2)
const iso = (d: Date) => d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate())
const TODAY = iso(today)
const IN_10_DAYS = iso(new Date(today.getFullYear(), today.getMonth(), today.getDate() + 10))
const YESTERDAY = iso(new Date(today.getFullYear(), today.getMonth(), today.getDate() - 1))

function clientLite(id: number, name: string, ours: boolean) {
  return {
    id,
    name,
    is_our_client: ours,
    phone: ours ? '0757-8288' : null,
    address: null,
    client_type: 'legal',
    client_type_label: '法人',
    id_number: null,
    legal_representative: ours ? '刘某' : null,
    legal_representative_id_number: null,
    identity_docs: [],
  }
}

function makeContract(over: Partial<ContractListItem> = {}): ContractListItem {
  return {
    id: 7,
    name: '某银行与某公司金融借款合同纠纷诉讼委托合同',
    case_type: 'civil',
    case_type_label: '民商事',
    status: 'active',
    status_label: '在办',
    specified_date: '2025-03-01',
    start_date: '2025-03-12',
    end_date: null,
    is_filed: true,
    filing_number: '2025_MS_HT_0031',
    fee_mode: '半风险',
    fixed_amount: '50000',
    risk_rate: '8',
    custom_terms: '风险部分按回款 8% 结算',
    representation_stages: ['一审', '二审'],
    law_firm_oa_url: null,
    law_firm_oa_case_number: null,
    has_matched_templates: false,
    can_archive: false,
    case_count: 2,
    total_received: 50000,
    total_invoiced: 0,
    unpaid_amount: null,
    contract_parties: [
      { id: 1, contract: 7, client: 1, role: 'principal', role_label: '委托人', client_detail: clientLite(1, '某银行', true) },
      { id: 2, contract: 7, client: 2, role: 'opponent', role_label: '对方当事人', client_detail: clientLite(2, '某公司', false) },
    ],
    assignments: [{ id: 1, lawyer_id: 1, lawyer_name: '黄崧', is_primary: true, order: 0 }],
    primary_lawyer: { id: 1, username: 'hs', real_name: '黄崧', phone: '138', law_firm_name: '某律所' },
    reminders: [
      {
        id: 1,
        contract_id: 7,
        reminder_type: 'other',
        reminder_type_label: '其他',
        content: '合同直挂期限',
        due_at: IN_10_DAYS + 'T09:00:00+08:00',
        created_at: '2026-01-01T00:00:00Z',
        updated_at: '2026-01-01T00:00:00Z',
      },
    ],
    payments: [
      { id: 1, contract: 7, amount: '50000', received_at: '2025-03-15', note: '前期律师费', invoice_status: 'issued', invoice_status_label: '已开票' } as ContractListItem['payments'][number],
    ],
    client_payment_records: [],
    supplementary_agreements: [],
    ...over,
  }
}

function makeCase(over: Partial<CaseListItem> = {}): CaseListItem {
  return {
    id: 1,
    name: '某银行诉某公司金融借款合同纠纷',
    status: '在办',
    is_filed: true,
    filing_number: null,
    case_type: 'civil',
    start_date: '2025-03-17',
    effective_date: null,
    specified_date: null,
    target_amount: '3200000',
    preservation_amount: '1600000',
    cause_of_action: '金融借款合同纠纷',
    current_stage: '一审',
    contract_id: 7,
    parties: [
      { id: 1, case: 1, client: 1, legal_status: '原告', client_detail: clientLite(1, '某银行', true) },
      { id: 2, case: 1, client: 2, legal_status: '被告', client_detail: clientLite(2, '某公司', false) },
    ],
    assignments: [],
    logs: [],
    case_numbers: [{ id: 1, number: '（2025）粤0605民初1234号', remarks: '', created_at: '2025-04-02T00:00:00Z' }], // privacy-allow 虚构案号
    supervising_authorities: [
      { id: 1, name: '佛山市南海区人民法院', authority_type: 'trial', authority_type_display: '法院', created_at: '2025-03-17T00:00:00Z' },
    ],
    chats: [],
    contacts: [],
    ...over,
  }
}

const lawyers: LawyerListItem[] = [
  { id: 1, username: 'hs', real_name: '黄崧', phone: '138', license_no: '1440120', law_firm_detail: { id: 1, name: '某律所' } },
]

function setupUi(path = '/cases/7') {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/cases" element={<div>cases-list</div>} />
          <Route path="/cases/:id" element={<DealDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  Element.prototype.scrollIntoView = vi.fn()
  getContractMock.mockResolvedValue(makeContract())
  lawyersMock.mockResolvedValue(lawyers)
  casesMock.mockResolvedValue([
    // 故意乱序给：二审（2026）在前、一审（2025）在后，页面应按收案日期排
    makeCase({
      id: 2,
      name: '某公司与某银行金融借款合同纠纷二审',
      current_stage: '二审',
      start_date: '2026-03-05',
      target_amount: null,
      preservation_amount: null,
      case_numbers: [{ id: 2, number: '（2026）粤06民终887号', remarks: '', created_at: '2026-03-05T00:00:00Z' }], // privacy-allow 虚构案号
      supervising_authorities: [
        { id: 2, name: '佛山市中级人民法院', authority_type: 'trial', authority_type_display: '法院', created_at: '2026-03-05T00:00:00Z' },
      ],
      parties: [
        { id: 3, case: 2, client: 1, legal_status: '被上诉人', client_detail: clientLite(1, '某银行', true) },
        { id: 4, case: 2, client: 2, legal_status: '上诉人', client_detail: clientLite(2, '某公司', false) },
      ],
      logs: [
        {
          id: 11, case: 2, content: '二审立案', actor: 1, created_at: '2026-03-05T10:00:00+08:00', updated_at: '2026-03-05T10:00:00+08:00',
          actor_detail: { id: 1, username: 'zm', real_name: '周明' }, attachments: [], reminders: [],
        },
        {
          id: 10, case: 2, content: '收到上诉状', actor: 1, created_at: '2026-02-02T09:00:00+08:00', updated_at: '2026-02-02T09:00:00+08:00',
          actor_detail: { id: 1, username: 'hs', real_name: '黄崧' },
          attachments: [{ id: 1, log: 10, file_path: 'a.pdf', media_url: null, uploaded_at: '2026-02-02T09:00:00+08:00', original_filename: 'a.pdf' }],
          reminders: [
            {
              id: 30, case_log_id: 10, reminder_type: 'submission_deadline', reminder_type_label: '材料',
              content: '补充代理意见递交', due_at: TODAY + 'T18:00:00+08:00',
              created_at: '2026-02-02T09:00:00+08:00', updated_at: '2026-02-02T09:00:00+08:00',
            },
          ],
        },
      ],
      contacts: [
        {
          id: 1, name: '梁某', role: 'clerk', role_display: '书记员', phone: '0757-8332', address: null, stage: '', stage_display: null,
          note: '', authority_name: '佛山市中级人民法院', authority_id: 2, case_id: 2, created_at: '2026-03-05T00:00:00Z', updated_at: '2026-03-05T00:00:00Z',
        },
      ],
    }),
    makeCase({ id: 1, status: '已结案' }),
  ])
  remindersMock.mockImplementation(async (caseId: number): Promise<ReminderOut[]> =>
    caseId === 2
      ? [
          {
            id: 40, case: 2, reminder_type: 'hearing', reminder_type_label: '开庭', content: '二审开庭',
            due_at: IN_10_DAYS + 'T09:30:00+08:00', is_completed: false,
            created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
          },
          {
            id: 41, case: 2, reminder_type: 'other', reminder_type_label: '其他', content: '已完成的不该出现',
            due_at: IN_10_DAYS + 'T09:30:00+08:00', is_completed: true,
            created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
          },
          {
            id: 42, case: 2, reminder_type: 'other', reminder_type_label: '其他', content: '昨天的已过期',
            due_at: YESTERDAY + 'T09:30:00+08:00', is_completed: false,
            created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
          },
        ]
      : [],
  )
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('DealDetailPage 加载与页头', () => {
  it('加载中给 spinner 文案；到达后主标题即合同名，meta 含类型/状态/我方→对方/建档/主办', async () => {
    setupUi()
    expect(screen.getByText('正在加载委托…')).toBeTruthy()
    const h1 = await screen.findByRole('heading', { level: 1 })
    expect(h1.textContent).toBe('某银行与某公司金融借款合同纠纷诉讼委托合同')
    expect(screen.getByText('民商事')).toBeTruthy()
    expect(screen.getByText('某银行 → 某公司')).toBeTruthy()
    // 建档编号同时出现在页头 meta 与档案「合同要素」里，两处都是真实字段
    expect(screen.getAllByText('2025_MS_HT_0031').length).toBeGreaterThanOrEqual(1)
    expect(getContractMock).toHaveBeenCalledWith(7)
    expect(casesMock).toHaveBeenCalledWith(7)
  })

  it('非法 id 直接重定向回办案主页，不发请求', async () => {
    setupUi('/cases/abc')
    expect(await screen.findByText('cases-list')).toBeTruthy()
    expect(getContractMock).not.toHaveBeenCalled()
  })

  it('合同加载失败：错误文案（errMessage 透传可读 message）+ 重试 + 返回办案', async () => {
    getContractMock.mockRejectedValueOnce(new Error('boom'))
    setupUi()
    expect(await screen.findByText(/boom/)).toBeTruthy()
    expect(screen.getByText('返回办案')).toBeTruthy()
    expect(screen.getByText('重试')).toBeTruthy()
  })

  it('非诉委托：不渲染诉讼骨架，给设计中提示与返回入口', async () => {
    getContractMock.mockResolvedValueOnce(makeContract({ case_type: 'advisor', case_type_label: '常年法律顾问' }))
    setupUi()
    expect(await screen.findByText(/非诉详情页正在设计中/)).toBeTruthy()
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull()
  })
})

describe('DealDetailPage 程序链与案件节', () => {
  it('stepper 按收案日期排（一审 → 二审），尾随「执行 未启动」虚节点；摘要计数', async () => {
    setupUi()
    await screen.findByRole('heading', { level: 1 })
    const jump1 = await screen.findByTitle('跳到 一审')
    const jump2 = screen.getByTitle('跳到 二审')
    expect(jump1.compareDocumentPosition(jump2) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    expect(screen.getByTitle('未启动')).toBeTruthy()
    expect(screen.getByText('2 个案件 · 一审 → 二审')).toBeTruthy()
    expect(screen.getByText('＋ 立执行案')).toBeTruthy()
  })

  it('案件节：案号 chip、meta 机构/收案/案由/标的/保全、诉讼地位随案变化、日志升序叙事', async () => {
    setupUi()
    await screen.findByRole('heading', { level: 1 })
    const sec2 = await waitFor(() => {
      const el = document.getElementById('case-2')
      if (!el) throw new Error('case-2 not yet')
      return el
    })
    expect(within(sec2).getByText('（2026）粤06民终887号')).toBeTruthy() // privacy-allow 虚构案号
    expect(within(sec2).getByText('佛山市中级人民法院')).toBeTruthy()
    expect(within(sec2).getByText('被上诉人')).toBeTruthy()
    expect(within(sec2).getByText('上诉人')).toBeTruthy()
    const logs = within(sec2).getAllByText(/收到上诉状|二审立案/).map((n) => n.textContent)
    expect(logs).toEqual(['收到上诉状', '二审立案'])
    expect(within(sec2).getByText(/📎 1/)).toBeTruthy()

    const sec1 = document.getElementById('case-1')!
    expect(within(sec1).getByText('已结')).toBeTruthy()
    expect(within(sec1).getByText('¥3,200,000')).toBeTruthy()
    expect(within(sec1).getByText('¥1,600,000')).toBeTruthy()
    expect(within(sec1).getByText('还没有办案日志')).toBeTruthy()
  })

  it('stepper 点击滚到对应案件节', async () => {
    setupUi()
    const jump = await screen.findByTitle('跳到 二审')
    jump.click()
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled()
  })
})

describe('DealDetailPage 右栏与档案', () => {
  it('期限三源合流按到期升序：今日日志级标红在前、合同直挂、案件直挂开庭；已完成与过期剔除', async () => {
    setupUi()
    await screen.findByText('二审开庭')
    const list = screen.getByText('期限').parentElement!.parentElement!
    const items = within(list).getAllByText(/补充代理意见递交|合同直挂期限|二审开庭/).map((n) => n.textContent ?? '')
    // 今日的日志级提醒排第一，且带类型标签「材料」在同一行内
    expect(items[0]).toMatch(/补充代理意见递交/)
    expect(items[0]).toMatch(/^材料/)
    expect(items).toHaveLength(3)
    expect(within(list).getByText(/· 今天/)).toBeTruthy()
    expect(screen.queryByText('已完成的不该出现')).toBeNull()
    expect(screen.queryByText('昨天的已过期')).toBeNull()
    expect(remindersMock).toHaveBeenCalledWith(1)
    expect(remindersMock).toHaveBeenCalledWith(2)
  })

  it('法院联系人按机构分组、律师带证号、涉案与收费取链上标的与合同费用', async () => {
    setupUi()
    await screen.findByText('梁某')
    expect(screen.getByText('法院联系人')).toBeTruthy()
    expect(screen.getAllByText('佛山市中级人民法院').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByText(/执业证号 1440120/)).toBeTruthy()
    expect(screen.getByText('标的额')).toBeTruthy()
    expect(screen.getByText('¥50,000 · 半风险')).toBeTruthy()
    // 风险比例在右栏「涉案与收费」与档案「合同要素」各出现一次
    expect(screen.getAllByText('8%')).toHaveLength(2)
  })

  it('档案沉底：当事人（我方在前 + 角色标签）、合同要素、收款表', async () => {
    setupUi()
    await screen.findByText('当事人')
    expect(screen.getByText('委托人')).toBeTruthy()
    expect(screen.getByText('对方当事人')).toBeTruthy()
    expect(screen.getByText('合同要素')).toBeTruthy()
    expect(screen.getByText('收款')).toBeTruthy()
    expect(screen.getByText(/前期律师费/)).toBeTruthy()
    expect(screen.getByText('＋ 记收款')).toBeTruthy()
  })
})
