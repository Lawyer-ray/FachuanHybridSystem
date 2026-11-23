// @vitest-environment jsdom
/**
 * 「可能关联的在办项目」面板（ContractMatchPanel）。
 *
 * 锁定：
 * 1. 有候选时列出项目名与**匹配理由**（律师要靠理由判断对错，不能只给名字）；
 * 2. 无候选时明确说「等待人工关联」，并回显系统识别到的案号/金额；
 * 3. 匹配接口挂掉时降级为「请手动关联」，不把技术错误抛给用户。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen } from '@testing-library/react'
import type { ReactNode } from 'react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  getContractMatch: vi.fn(),
}))

vi.mock('./api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./api')>()
  return { ...actual, getContractMatch: apiMock.getContractMatch }
})

import { ContractMatchPanel } from './components/ContractMatchPanel'

function wrap(ui: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </MemoryRouter>
  )
}

beforeEach(() => {
  apiMock.getContractMatch.mockReset()
})

describe('ContractMatchPanel', () => {
  it('有候选时列出项目名与匹配理由', async () => {
    apiMock.getContractMatch.mockResolvedValue({
      status: 'suggested',
      candidates: [
        {
          contract_id: 160,
          contract_name: '某某诉某公司合同纠纷一案',
          score: 0.45,
          reasons: ['当事人命中 某某'],
          outstanding_amount: '67044.53',
          fee_mode: 'SEMI_RISK',
          caveat: '',
        },
      ],
      extracted_amounts: ['2400'],
      extracted_case_numbers: [],
    })

    render(wrap(<ContractMatchPanel messageId={533} />))

    expect(await screen.findByText('某某诉某公司合同纠纷一案')).toBeTruthy()
    // 理由必须显示：律师据此判断匹配对错
    expect(screen.getByText(/当事人命中/)).toBeTruthy()
    // 半风险要标出来，律师一看就知道金额口径和其他合同不同
    expect(screen.getByText('半风险')).toBeTruthy()
    expect(screen.getByText(/应收余额/)).toBeTruthy()
  })

  it('无候选时说明等待人工关联，并回显识别到的信号', async () => {
    apiMock.getContractMatch.mockResolvedValue({
      status: 'none',
      candidates: [],
      extracted_amounts: ['2400'],
      extracted_case_numbers: ['（2026）粤0604民初1号'], // privacy-allow
    })

    render(wrap(<ContractMatchPanel messageId={533} />))

    expect(await screen.findByText(/等待人工关联/)).toBeTruthy()
    expect(screen.getByText(/（2026）粤0604民初1号/)).toBeTruthy() // privacy-allow
    expect(screen.getByText(/2400/)).toBeTruthy()
  })

  it('接口失败时降级为请手动关联，不抛技术错误', async () => {
    apiMock.getContractMatch.mockRejectedValue(new Error('boom'))

    render(wrap(<ContractMatchPanel messageId={533} />))

    expect(await screen.findByText(/请手动在项目中关联/)).toBeTruthy()
    expect(screen.queryByText(/boom/)).toBeNull()
  })

  it('展示 caveat（如全风险缺标的额：需人工核对）', async () => {
    apiMock.getContractMatch.mockResolvedValue({
      status: 'suggested',
      candidates: [
        {
          contract_id: 334,
          contract_name: '全风险测试合同',
          score: 0.2,
          reasons: ['当事人命中 张三'],
          outstanding_amount: null,
          fee_mode: 'FULL_RISK',
          caveat: '案件标的额未填，无法推算风险收费',
        },
      ],
      extracted_amounts: [],
      extracted_case_numbers: [],
    })

    render(wrap(<ContractMatchPanel messageId={1} />))

    expect(await screen.findByText(/无法推算风险收费/)).toBeTruthy()
  })
})
