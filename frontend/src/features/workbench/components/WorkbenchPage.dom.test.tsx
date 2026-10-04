// @vitest-environment jsdom
/**
 * WorkbenchPage（办案主页）组件渲染单测（jsdom + 真实 timers）。
 *
 * mock 边界：../api 三个接口 + 顶部导航 AppNavbar（子组件桩）。
 * 覆盖：加载/错误态、类型分组渲染与摘要、FilterBar 搜索防抖下推与筛选面板交互、
 * 两种空态分支（真空库 / 筛选后为空 → 清除筛选出口，最近修复的死分支回归）、
 * 分页按钮状态与翻页下推、错误重试。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  listContractsPage: vi.fn(),
  listLawyers: vi.fn(),
  listCasesByContract: vi.fn(),
}))
vi.mock('@/components/shared/AppNavbar', () => ({
  AppNavbar: () => <nav>navbar-stub</nav>,
}))

import { listContractsPage, listLawyers } from '../api'
import type { ContractListItem, ContractPageResponse, LawyerListItem } from '../types'

import { WorkbenchPage } from './WorkbenchPage'

const listPageMock = vi.mocked(listContractsPage)
const lawyersMock = vi.mocked(listLawyers)

function makeContract(id: number, name: string, over: Partial<ContractListItem> = {}): ContractListItem {
  return {
    id,
    name,
    case_type: 'civil',
    case_type_label: '民事诉讼',
    status: 'active',
    status_label: '在办',
    specified_date: null,
    start_date: '2026-09-01',
    end_date: null,
    is_filed: false,
    filing_number: null,
    fee_mode: '固定收费',
    fixed_amount: 10000,
    risk_rate: null,
    custom_terms: null,
    representation_stages: [],
    law_firm_oa_url: null,
    law_firm_oa_case_number: null,
    case_count: 1,
    total_received: null,
    total_invoiced: null,
    unpaid_amount: null,
    contract_parties: [],
    assignments: [],
    primary_lawyer: null,
    reminders: [],
    payments: [],
    client_payment_records: [],
    supplementary_agreements: [],
    ...over,
  }
}

const lawyers: LawyerListItem[] = [
  { id: 1, username: 'zhang', real_name: '张律师', phone: '13800000000', license_no: '137xxx', law_firm_detail: { id: 1, name: '发川律所' } },
]

function makePage(partial: Partial<ContractPageResponse> = {}): ContractPageResponse {
  return {
    items: [makeContract(1, '王五委托')],
    total: 1,
    page: 1,
    page_size: 50,
    status_counts: { active: 1 },
    cat_counts: [
      { value: 'civil', label: '民事诉讼', n: 3 },
      { value: 'advisor', label: '法律顾问', n: 2 },
    ],
    fee_counts: [],
    ...partial,
  }
}

function setupUi() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WorkbenchPage />
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

beforeEach(() => {
  vi.clearAllMocks()
  // jsdom 未实现 scrollTo（gotoPage 翻页会调用），打桩避免噪音
  window.scrollTo = vi.fn()
  listPageMock.mockResolvedValue(makePage())
  lawyersMock.mockResolvedValue(lawyers)
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('WorkbenchPage 加载 / 错误态', () => {
  it('首屏加载中：展示加载文案，不出列表', () => {
    listPageMock.mockReturnValue(new Promise(() => {}))
    setupUi()
    expect(screen.getByText('正在加载办案数据…')).toBeTruthy()
    expect(screen.queryByText('王五委托')).toBeNull()
  })

  it('列表接口失败：展示错误文案与重试按钮；点重试重新请求', async () => {
    listPageMock.mockRejectedValueOnce(new Error('网络中断')).mockResolvedValue(makePage())
    setupUi()
    expect(await screen.findByText('网络中断')).toBeTruthy()
    const calls = listPageMock.mock.calls.length
    fireEvent.click(screen.getByRole('button', { name: '重试' }))
    await waitFor(() => expect(listPageMock.mock.calls.length).toBeGreaterThan(calls))
  })
})

describe('WorkbenchPage 分组渲染', () => {
  it('按 case_type_label 分组：诉讼组在前，组头带数量，行内可见合同名', async () => {
    listPageMock.mockResolvedValue(
      makePage({
        items: [
          makeContract(2, '赵六法律顾问', { case_type: 'advisor', case_type_label: '法律顾问' }),
          makeContract(1, '王五委托', { case_type: 'civil', case_type_label: '民事诉讼' }),
        ],
        total: 2,
        status_counts: { active: 2 },
      }),
    )
    setupUi()
    expect(await screen.findByText('王五委托')).toBeTruthy()
    expect(screen.getByText('赵六法律顾问')).toBeTruthy()
    const litHeader = screen.getByText('民事诉讼')
    const nonLitHeader = screen.getByText('法律顾问')
    // 未选类目时诉讼组在前
    expect(
      litHeader.compareDocumentPosition(nonLitHeader) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    // 摘要：totalContracts 取 facets 口径
    expect(
      screen.getByText((_, el) => el?.tagName === 'SPAN' && el.textContent === '2 个合同 · 2 在办'),
    ).toBeTruthy()
  })
})

describe('WorkbenchPage FilterBar 交互下推', () => {
  it('搜索框输入：防抖 300ms 后关键词 trim 下推到列表接口', async () => {
    setupUi()
    await screen.findByText('王五委托')
    fireEvent.change(screen.getByPlaceholderText('搜索合同（名称）'), { target: { value: '  王五 ' } })
    await waitFor(
      () => expect(listPageMock).toHaveBeenLastCalledWith(expect.objectContaining({ q: '王五' })),
      { timeout: 2000 },
    )
  })

  it('筛选面板选类目 chip：cat 代码值下推到列表接口', async () => {
    setupUi()
    await screen.findByText('王五委托')
    fireEvent.click(screen.getByRole('button', { name: /筛选/ }))
    // chip 可访问名是「标签+计数」紧拼（如「民事诉讼3」），用正则容忍
    fireEvent.click(screen.getByRole('button', { name: /^民事诉讼/ }))
    await waitFor(() =>
      expect(listPageMock).toHaveBeenLastCalledWith(expect.objectContaining({ cat: 'civil' })),
    )
  })
})

describe('WorkbenchPage 空态两分支', () => {
  it('真空库（facets 全库为 0）：提示还没有合同数据，不给清除筛选', async () => {
    listPageMock.mockResolvedValue(makePage({ items: [], total: 0, status_counts: {} }))
    setupUi()
    expect(await screen.findByText('还没有合同数据')).toBeTruthy()
    expect(screen.queryByText('清除筛选')).toBeNull()
  })

  it('筛选后为空（全库有数据）：给清除筛选出口，点击后回默认筛选重查（回归）', async () => {
    const dataPage = makePage({ total: 3, status_counts: { active: 3 } })
    const emptyFiltered = makePage({ items: [], total: 0, status_counts: { active: 3 } })
    listPageMock.mockImplementation(async (opts) => (opts.q ? emptyFiltered : dataPage))
    setupUi()
    await screen.findByText('王五委托')

    fireEvent.change(screen.getByPlaceholderText('搜索合同（名称）'), { target: { value: '不存在' } })
    expect(await screen.findByText('没有匹配的合同')).toBeTruthy()
    expect(screen.queryByText('还没有合同数据')).toBeNull()

    fireEvent.click(screen.getByRole('button', { name: '清除筛选' }))
    // 清除后回到默认 queryKey（60s staleTime 内命中缓存，不再重发请求）——
    // 断言 UI 恢复默认视图 + 搜索框被清空，而非断言新请求
    expect(await screen.findByText('王五委托')).toBeTruthy()
    await waitFor(() =>
      expect(screen.getByPlaceholderText('搜索合同（名称）')).toHaveProperty('value', ''),
    )
  })
})

describe('WorkbenchPage 分页', () => {
  it('多页数据：页码信息正确，上一页首屏禁用，翻页下推 page', async () => {
    listPageMock.mockImplementation(async (opts) =>
      makePage({ page: opts.page, total: 120, page_size: 50 }),
    )
    setupUi()
    expect(await screen.findByText('第 1 / 3 页 · 共 120 个')).toBeTruthy()

    const prev = screen.getByRole('button', { name: '‹ 上一页' }) as HTMLButtonElement
    expect(prev.disabled).toBe(true)

    fireEvent.click(screen.getByRole('button', { name: '下一页 ›' }))
    expect(await screen.findByText('第 2 / 3 页 · 共 120 个')).toBeTruthy()
    expect(listPageMock).toHaveBeenLastCalledWith(expect.objectContaining({ page: 2 }))
    // fetching 态解除后（keepPreviousData 期间 fetching=true 也会禁用翻页按钮）
    await waitFor(() =>
      expect((screen.getByRole('button', { name: '‹ 上一页' }) as HTMLButtonElement).disabled).toBe(false),
    )

    fireEvent.click(screen.getByRole('button', { name: '下一页 ›' }))
    expect(await screen.findByText('第 3 / 3 页 · 共 120 个')).toBeTruthy()
    await waitFor(() =>
      expect((screen.getByRole('button', { name: '下一页 ›' }) as HTMLButtonElement).disabled).toBe(true),
    )
  })

  it('单页数据：不渲染分页条', async () => {
    setupUi()
    await screen.findByText('王五委托')
    expect(screen.queryByText(/下一页/)).toBeNull()
  })
})
