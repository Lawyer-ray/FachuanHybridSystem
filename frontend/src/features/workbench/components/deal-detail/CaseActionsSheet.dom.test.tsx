// @vitest-environment jsdom
/**
 * 「办理」抽屉：四行动作的就绪状态与「缺凭证就禁用」。
 *
 * 这里**不断言真的提交**（那是法院/OA 的不可逆动作）——只钉两件：
 * 1. 打开抽屉就会去读四项只读就绪信息（法院账号 / 有无案号 / OA 凭证 / 案卷清单）；
 * 2. 缺凭证或清单不齐时按钮禁用，原因写在行里。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getFilingInfo: vi.fn(),
  getGuaranteeInfo: vi.fn(),
  listOaFilingConfigs: vi.fn(),
  getArchiveChecklist: vi.fn(),
  startFiling: vi.fn(),
  startGuarantee: vi.fn(),
  startOaFiling: vi.fn(),
  archiveContract: vi.fn(),
  getFilingSession: vi.fn(),
  getGuaranteeSession: vi.fn(),
  getOaFilingSession: vi.fn(),
}))
vi.mock('../../api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../api')>()),
  ...api,
}))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { CaseActionsSheet } from './CaseActionsSheet'

function wrap(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}>{ui}</QueryClientProvider>)
}

const FILING = {
  case_id: 488,
  case_name: '某案',
  court_name: '某某人民法院',
  cause_of_action: '买卖合同纠纷',
  target_amount: '1000.00',
  our_party_is_plaintiff_side: true,
  has_court_credential: true,
  has_http_plugin: true,
  plugin_available: true,
  suggested_filing_type: 'civil',
  default_filing_engine: 'api',
}

beforeEach(() => {
  vi.clearAllMocks()
  api.getFilingInfo.mockResolvedValue(FILING)
  api.getGuaranteeInfo.mockResolvedValue({
    case_id: 488, case_name: '某案', court_name: '某某人民法院', cause_of_action: null,
    preserve_amount: null, preserve_category: '诉前保全', has_case_number: false,
    has_court_credential: true, our_party_is_plaintiff_side: true,
    insurance_company_name: '阳光财险', insurance_company_options: ['阳光财险'],
  })
  api.listOaFilingConfigs.mockResolvedValue([{ id: 'OA1', oa_system_name: '某OA', has_credential: true }])
  api.getArchiveChecklist.mockResolvedValue({
    archive_category: 'litigation', archive_category_label: '诉讼/仲裁', compact_archive: false,
    items: [{ code: 'lt_1', name: '案卷封面', required: true, completed: true }],
  })
})

describe('CaseActionsSheet', () => {
  it('四行都渲染，并读到各自的就绪状态', async () => {
    wrap(<CaseActionsSheet open onClose={vi.fn()} caseId={488} caseLabel="一审" contractId={448} onChanged={vi.fn()} />)

    expect(await screen.findByText('办理 · 一审')).toBeTruthy()
    expect(await screen.findByText(/法院账号已配/)).toBeTruthy()
    expect(screen.getByText(/诉前保全/)).toBeTruthy()
    expect(screen.getByText(/某OA · 凭证已配/)).toBeTruthy()
    expect(screen.getByText(/案卷清单 1\/1 齐备/)).toBeTruthy()
    expect(api.getFilingInfo).toHaveBeenCalledWith(488)
    expect(api.listOaFilingConfigs).toHaveBeenCalled()
    expect(api.getArchiveChecklist).toHaveBeenCalledWith(448)
    // 只是打开看一看，不能自己发提交
    expect(api.startFiling).not.toHaveBeenCalled()
    expect(api.archiveContract).not.toHaveBeenCalled()
  })

  it('缺法院账号 / 缺 OA 凭证 / 案卷不齐时，对应按钮禁用', async () => {
    api.getFilingInfo.mockResolvedValue({ ...FILING, has_court_credential: false })
    api.listOaFilingConfigs.mockResolvedValue([{ id: 'OA1', oa_system_name: '某OA', has_credential: false }])
    api.getArchiveChecklist.mockResolvedValue({
      archive_category: 'litigation', archive_category_label: '诉讼/仲裁', compact_archive: false,
      items: [{ code: 'lt_2', name: '结案归档登记表', required: true, completed: false }],
    })

    wrap(<CaseActionsSheet open onClose={vi.fn()} caseId={488} caseLabel="一审" contractId={448} onChanged={vi.fn()} />)

    expect(await screen.findByText(/缺法院账号/)).toBeTruthy()
    await waitFor(() =>
      expect((screen.getByRole('button', { name: '开始立案' }) as HTMLButtonElement).disabled).toBe(true),
    )
    expect((screen.getByRole('button', { name: '提交 OA' }) as HTMLButtonElement).disabled).toBe(true)
    expect((screen.getByRole('button', { name: '归档项目' }) as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/缺：结案归档登记表/)).toBeTruthy()
  })
})
