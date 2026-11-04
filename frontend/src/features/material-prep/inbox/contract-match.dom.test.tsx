// @vitest-environment jsdom
/**
 * 「可能关联的在办项目」面板 + 邮件 HTML 正文渲染。
 *
 * 锁定：
 * 1. 有候选时列出项目名与**匹配理由**（律师要靠理由判断对错，不能只给名字）；
 * 2. 无候选时明确说「等待人工关联」，并回显系统识别到的案号/金额；
 * 3. 匹配接口挂掉时降级为「请手动关联」，不把技术错误抛给用户；
 * 4. 只有 HTML 正文的邮件（银行到账通知）必须真的渲染出来，不能白屏。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
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
import { MailHtmlBody } from './components/MailHtmlBody'

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

describe('MailHtmlBody', () => {
  it('用 sandboxed iframe 渲染，且不授予脚本权限', async () => {
    render(<MailHtmlBody html="<html><body><p>存入人民币 2400 元</p></body></html>" />)

    const frame = await screen.findByTitle('邮件正文')
    // 安全边界：这两个属性都不能出现
    const sandbox = frame.getAttribute('sandbox') ?? ''
    expect(sandbox).not.toContain('allow-scripts')
    expect(sandbox).not.toContain('allow-same-origin')
    // 正文内容应写进 srcDoc
    await waitFor(() => {
      expect(frame.getAttribute('srcdoc')).toContain('2400')
    })
  })

  it('剥掉邮件自带 html/head 外壳，只留 body 内容', async () => {
    render(
      <MailHtmlBody html="<html><head><style>p{color:red}</style></head><body><p>正文在</p></body></html>" />,
    )

    const frame = await screen.findByTitle('邮件正文')
    const doc = frame.getAttribute('srcdoc') ?? ''
    expect(doc).toContain('正文在')
    // 邮件自带的 head 内容不应出现（会被我们注入的样式覆盖，导致排版错乱）
    expect(doc).not.toContain('color:red')
  })
})
