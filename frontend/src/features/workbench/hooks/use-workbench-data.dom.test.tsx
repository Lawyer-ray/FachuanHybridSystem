// @vitest-environment jsdom
/**
 * useWorkbenchData 单测（jsdom + 真实 timers）。
 *
 * mock 只打 api 层（../api）：listContractsPage / listLawyers。
 * 覆盖：过滤参数下推（queryKey 变化触发新查询）、搜索词防抖 + trim、
 * total/totalPages/facets 映射、两源合并、错误文案与 refetch。
 * 防抖 300ms 用真实短等待断言（fake timers 与 RTL waitFor 的 jest 探测不兼容，不引入）。
 */
import { type ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('../api', () => ({
  listContractsPage: vi.fn(),
  listLawyers: vi.fn(),
}))

import { listContractsPage, listLawyers } from '../api'
import type { ContractListItem, ContractPageResponse, LawyerListItem } from '../types'

import { useWorkbenchData, workbenchKeys } from './use-workbench-data'
import type { WorkbenchFilter } from '../types'

// 被 vi.mock 的模块函数经 vi.mocked 拿到带 mock 属性的类型视图
const listPageMock = vi.mocked(listContractsPage)
const lawyersMock = vi.mocked(listLawyers)

const baseFilter: WorkbenchFilter = { status: '', cat: '', fee: '', q: '' }

function makeContract(id: number, name: string): ContractListItem {
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
  }
}

const lawyers: LawyerListItem[] = [
  {
    id: 1,
    username: 'zhang',
    real_name: '张律师',
    phone: '13800000000',
    license_no: '13700...',
    law_firm_detail: { id: 1, name: '发川律所' },
  },
]

function makePage(partial: Partial<ContractPageResponse> = {}): ContractPageResponse {
  return {
    items: [makeContract(1, '王五委托')],
    total: 0,
    page: 1,
    page_size: 50,
    status_counts: {},
    cat_counts: [],
    fee_counts: [],
    ...partial,
  }
}

function setup(initialFilter: WorkbenchFilter = baseFilter, initialPage = 1) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  })
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  const utils = renderHook(({ filter, page }) => useWorkbenchData(filter, page), {
    wrapper,
    initialProps: { filter: initialFilter, page: initialPage },
  })
  return { ...utils, queryClient }
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms))

beforeEach(() => {
  vi.clearAllMocks()
  listPageMock.mockResolvedValue(makePage())
  lawyersMock.mockResolvedValue(lawyers)
})

afterEach(() => {
  vi.clearAllMocks()
})

describe('useWorkbenchData 过滤参数下推', () => {
  it('status/cat/fee/page 随 queryKey 变化下推到 listContractsPage', async () => {
    const { result, rerender } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(listContractsPage).toHaveBeenLastCalledWith({
      page: 1,
      status: '',
      cat: '',
      fee: '',
      q: '',
    })

    rerender({ filter: { ...baseFilter, status: 'active', cat: 'civil', fee: 'FIXED' }, page: 2 })
    await waitFor(() =>
      expect(listContractsPage).toHaveBeenLastCalledWith({
        page: 2,
        status: 'active',
        cat: 'civil',
        fee: 'FIXED',
        q: '',
      }),
    )
  })

  it('新过滤条件对应的新 queryKey 会在 queryClient 缓存中建立', async () => {
    const { result, queryClient, rerender } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    const nextFilter: WorkbenchFilter = { ...baseFilter, status: 'archived' }
    rerender({ filter: nextFilter, page: 1 })
    await waitFor(() =>
      expect(listContractsPage).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'archived' })),
    )
    expect(queryClient.getQueryState(workbenchKeys.contractPage(nextFilter, '', 1))).not.toBeNull()
  })
})

describe('useWorkbenchData 搜索防抖', () => {
  it('q 停止输入 300ms 才触发新查询，且 trim 后进参数', async () => {
    const { result, rerender } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    const callsBefore = listPageMock.mock.calls.length

    rerender({ filter: { ...baseFilter, q: '  王五  ' }, page: 1 })
    // 300ms 防抖窗口内（50ms < 300ms）不重查
    await sleep(60)
    expect(listPageMock.mock.calls.length).toBe(callsBefore)

    await waitFor(
      () => expect(listPageMock.mock.calls.length).toBe(callsBefore + 1),
      { timeout: 2000 },
    )
    expect(listContractsPage).toHaveBeenLastCalledWith(
      expect.objectContaining({ q: '王五' }),
    )
  })
})

describe('useWorkbenchData 结果映射', () => {
  it('total/totalPages 映射：total 120、page_size 50 → 3 页', async () => {
    listPageMock.mockResolvedValue(makePage({ total: 120, page: 3, page_size: 50 }))
    const { result } = setup()
    await waitFor(() => expect(result.current.total).toBe(120))
    expect(result.current.totalPages).toBe(3)
    expect(result.current.page).toBe(3)
  })

  it('totalPages 兜底至少 1 页（total=0 时不出现 0 页）', async () => {
    listPageMock.mockResolvedValue(makePage({ total: 0, items: [] }))
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.total).toBe(0)
    expect(result.current.totalPages).toBe(1)
  })

  it('facets 聚合：status_counts 求和为 totalContracts、activeCount 取 active', async () => {
    listPageMock.mockResolvedValue(
      makePage({ total: 120, status_counts: { active: 80, archived: 35, unsigned: 5 } }),
    )
    const { result } = setup()
    await waitFor(() => expect(result.current.facets).not.toBeNull())
    expect(result.current.totalContracts).toBe(120)
    expect(result.current.activeCount).toBe(80)
  })

  it('deals 由合同 × 律师两源合并：任一源未到时为空数组，双源到齐后产出', async () => {
    listPageMock.mockResolvedValue(makePage({ items: [makeContract(1, '王五委托')] }))
    let resolveLawyers!: (v: LawyerListItem[]) => void
    lawyersMock.mockReturnValue(
      new Promise<LawyerListItem[]>((resolve) => {
        resolveLawyers = resolve
      }),
    )
    const { result } = setup()

    await waitFor(() => expect(result.current.facets).not.toBeNull())
    // 律师源未到：deals 空
    expect(result.current.deals).toEqual([])

    resolveLawyers(lawyers)
    await waitFor(() => expect(result.current.deals.length).toBe(1))
    expect(result.current.deals[0]?.client).toBe('王五委托')
    expect(result.current.deals[0]?.caseCount).toBe(1)
  })

  it('列表接口失败：error 映射为后端可读文案', async () => {
    listPageMock.mockRejectedValue(new Error('网络中断'))
    const { result } = setup()
    await waitFor(() => expect(result.current.error).toBe('网络中断'))
    expect(result.current.deals).toEqual([])
  })

  it('refetch：同时触发列表与律师两个查询重取', async () => {
    const { result } = setup()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    const pageCalls = listPageMock.mock.calls.length
    const lawyerCalls = lawyersMock.mock.calls.length

    result.current.refetch()
    await waitFor(() => {
      expect(listPageMock.mock.calls.length).toBeGreaterThan(pageCalls)
      expect(lawyersMock.mock.calls.length).toBeGreaterThan(lawyerCalls)
    })
  })
})
