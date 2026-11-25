// @vitest-environment jsdom
/**
 * 待裁决回传件清单（jsdom）。
 *
 * mock 的是 `@/lib/api` 的 `createApiClient`，**不 mock `./api`**：这样这四个函数
 * 的 URL / 查询参数 / 请求体也一并被验证（`.json()` 之外没有别的活，形状由后端
 * schema 保证）。
 *
 * 锁四件事（每一件错了律师都会做出错误处置）：
 * 1. 三档 severity 都渲染出来且档位可分（红线 / 疑似 / 无法核对）；
 * 2. `pages_no_text > 0` 必须显式写「N 页无文本层，未核对」——否则律师以为整份都比过了；
 * 3. 「采纳改动」真的是 `action=accept`、「退回重签」是 `reject`（两个按钮调反了
 *    等于把客户改错的地方直接放行）；
 * 4. 空白清单说的是「本案没有待核对的回传件」，不是静默不渲染。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { toast } from 'sonner'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const kyMock = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('@/lib/api', () => ({ createApiClient: () => kyMock }))
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }))

import { PendingRuns } from './PendingRuns'
import type { VerifyRunOut } from './api'

/**
 * ky 的 `get/put/post` 返回的是「可 await 且带 .json()」的 ResponsePromise，
 * 而 `./api` 里写的是 `.get(...).json<T>()` —— 所以桩只给 `.json()` 一个能力即可。
 */
function jsonOf<T>(data: T) {
  return { json: async () => data }
}

/**
 * 失败路径：`./api` 拿到 .json() 才拒绝，等价于 ky 在取响应体时炸掉。
 * 断言里用的是 ky 的 HTTPError 形状（`{ name, data: { message } }` 的普通对象，
 * 与仓库里其他接口单测一致），所以这里把 reason 按 Error 传。
 */
function jsonFailed(error: unknown) {
  return { json: () => Promise.reject(error as Error) }
}

function finding(over: Partial<VerifyRunOut['findings'][number]>) {
  return {
    kind: 'field',
    code: 'code',
    title: '标题',
    severity: 'yellow',
    detail: '',
    expected: '',
    actual: '',
    page: null,
    ...over,
  }
}

/** 一件待裁决：三档发现项都齐（外加一条 yellow），覆盖度里有一页无文本层 */
function runOf(over: Partial<VerifyRunOut> = {}): VerifyRunOut {
  return {
    id: 3,
    artifact_id: 9,
    case_id: 7,
    doc_type: '起诉状',
    state: 'changed',
    state_label: '检出问题',
    tier: 1,
    inbound_file_name: '起诉状-回传.pdf',
    inbound_sha256: 'sha',
    page_count: 10,
    findings: [
      finding({
        kind: 'field',
        code: 'amount_changed',
        title: '借款金额被改',
        severity: 'red',
        detail: '与基线不一致',
        expected: '100000',
        actual: '120000',
        page: 2,
      }),
      finding({
        kind: 'paragraph',
        code: 'paragraph_missing',
        title: '诉请第二项缺失',
        severity: 'yellow',
        expected: '第二项存在',
        page: 3,
      }),
      finding({
        kind: 'coverage',
        code: 'page_no_text',
        title: '第 5 页无文本层',
        severity: 'gray',
        page: 5,
      }),
      finding({ code: 'date_changed', title: '落款日期被改', severity: 'yellow', page: 4 }),
    ],
    coverage: { pages_total: 10, pages_with_text: 9, pages_no_text: 1, text_compared: true },
    created_at: '2026-11-24T10:00:00+08:00',
    ...over,
  }
}

function renderPending(caseId = 7) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <PendingRuns caseId={caseId} />
    </QueryClientProvider>,
  )
  return { ...utils, queryClient }
}

beforeEach(() => {
  vi.clearAllMocks()
  kyMock.get.mockReturnValue(jsonOf([]))
  kyMock.post.mockReturnValue(
    jsonOf({
      id: 11,
      verification_id: 3,
      action: 'accept',
      reason: '',
      decided_by_id: 1,
      decided_at: '2026-11-24T11:00:00+08:00',
    }),
  )
})

describe('PendingRuns：空态', () => {
  it('没有待裁决件时写「本案没有待核对的回传件」', async () => {
    const { container } = renderPending()

    expect(await screen.findByText('本案没有待核对的回传件')).toBeTruthy()
    // 清单按案件拉：case_id 必须带上，否则后端拿不到案
    expect(kyMock.get).toHaveBeenCalledWith(
      'unverified',
      expect.objectContaining({ searchParams: { case_id: 7 } }),
    )
    container.remove()
  })
})

describe('PendingRuns：清单渲染', () => {
  it('文书名 + 状态 + 覆盖率（含「N 页无文本层，未核对」）', async () => {
    kyMock.get.mockReturnValue(jsonOf([runOf()]))
    const { container } = renderPending()

    expect(await screen.findByText('起诉状')).toBeTruthy()
    expect(screen.getByText('检出问题')).toBeTruthy()
    expect(
      screen.getByText('覆盖率 9/10 页 · 1 页无文本层，未核对'),
    ).toBeTruthy()
    container.remove()
  })

  it('三档 severity 各渲染一条：红线 / 疑似 / 无法核对，且带 expected → actual', async () => {
    kyMock.get.mockReturnValue(jsonOf([runOf()]))
    const { container } = renderPending()

    await screen.findByText('起诉状')
    const body = within(document.body)
    expect(body.getByText('红线')).toBeTruthy()
    expect(body.getByText('借款金额被改')).toBeTruthy()
    expect(body.getByText('100000 → 120000')).toBeTruthy()

    expect(body.getByText('疑似')).toBeTruthy()
    expect(body.getByText('诉请第二项缺失')).toBeTruthy()
    // expected 有、actual 空 → 空的一侧写成「（空）」，不留一个没有下文的箭头
    expect(body.getByText('第二项存在 → （空）')).toBeTruthy()

    expect(body.getByText('无法核对')).toBeTruthy()
    expect(body.getByText('第 5 页无文本层')).toBeTruthy()

    // 只摊开前三条：第四条不显示，但要说还剩几条，别让律师以为只有这些
    expect(body.queryByText('落款日期被改')).toBeNull()
    expect(body.getByText('还有 1 条未显示')).toBeTruthy()
    container.remove()
  })
})

describe('PendingRuns：裁决', () => {
  it('点「采纳改动」：POST decision 且 action=accept，成功后 toast 并重拉清单', async () => {
    kyMock.get.mockReturnValue(jsonOf([runOf()]))
    const { container } = renderPending()

    fireEvent.click(await screen.findByRole('button', { name: '采纳改动' }))

    await waitFor(() =>
      expect(kyMock.post).toHaveBeenCalledWith(
        'runs/3/decision',
        expect.objectContaining({ json: { action: 'accept', reason: '' } }),
      ),
    )
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('已采纳改动', expect.anything()))
    // 裁决过就不该留在清单里：失效重拉由后端口径决定
    await waitFor(() => expect(kyMock.get).toHaveBeenCalledTimes(2))
    container.remove()
  })

  it('点「退回重签」：action=reject', async () => {
    kyMock.get.mockReturnValue(jsonOf([runOf()]))
    const { container } = renderPending()

    fireEvent.click(await screen.findByRole('button', { name: '退回重签' }))

    await waitFor(() =>
      expect(kyMock.post).toHaveBeenCalledWith(
        'runs/3/decision',
        expect.objectContaining({ json: { action: 'reject', reason: '' } }),
      ),
    )
    await waitFor(() => expect(toast.success).toHaveBeenCalledWith('已退回重签', expect.anything()))
    container.remove()
  })

  it('裁决失败：用后端文案 toast，不静默吞掉', async () => {
    kyMock.get.mockReturnValue(jsonOf([runOf()]))
    kyMock.post.mockReturnValue(jsonFailed({ name: 'HTTPError', data: { message: '该件已有裁决' } }))
    const { container } = renderPending()

    fireEvent.click(await screen.findByRole('button', { name: '采纳改动' }))

    await waitFor(() =>
      expect(toast.error).toHaveBeenCalledWith('裁决失败：该件已有裁决'),
    )
    container.remove()
  })
})

describe('PendingRuns：覆盖度口径', () => {
  it('没有覆盖度键时不编数字，直接说未知', async () => {
    kyMock.get.mockReturnValue(jsonOf([runOf({ findings: [], coverage: {} })]))
    const { container } = renderPending()

    expect(await screen.findByText('覆盖度：未知')).toBeTruthy()
    container.remove()
  })

  it('全页都有文本层时不写多余的「N 页无文本层」', async () => {
    kyMock.get.mockReturnValue(
      jsonOf([runOf({ findings: [], coverage: { pages_total: 6, pages_with_text: 6, pages_no_text: 0 } })]),
    )
    const { container } = renderPending()

    expect(await screen.findByText('覆盖率 6/6 页')).toBeTruthy()
    container.remove()
  })

  it('后端只给总页数与缺文本页时按差值推算有文本层的页数', async () => {
    kyMock.get.mockReturnValue(
      jsonOf([runOf({ findings: [], coverage: { pages_total: 10, pages_no_text: 2 } })]),
    )
    const { container } = renderPending()

    expect(await screen.findByText('覆盖率 8/10 页 · 2 页无文本层，未核对')).toBeTruthy()
    container.remove()
  })
})
