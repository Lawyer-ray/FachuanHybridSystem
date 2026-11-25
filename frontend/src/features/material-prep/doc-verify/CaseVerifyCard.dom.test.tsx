// @vitest-environment jsdom
/**
 * 案件详情页的「回传件核对」历史卡（jsdom）。
 *
 * mock 的是 `@/lib/api` 的 `createApiClient`，**不 mock `./api`**：这样 `listCaseRuns`
 * 拼出来的 URL / 查询参数也一并被验证（`case_id`、`state`、`limit`、`offset` 错一个，
 * 律师看到的就是别的案件的记录，或者「筛选没反应」）。
 *
 * 锁五件事：
 * 1. 空态说的是「本案还没有核对记录」，不是静默不渲染；
 * 2. 三条记录都渲染出来，`pages_no_text > 0` 必须显式写「N 页无文本层，未核对」；
 * 3. 发现项的红/黄档位可分（render 时不能只剩标题）；
 * 4. 「加载更多」是**第二页请求**：`offset` 从 0 递增到 20，不是把首屏再拉一遍；
 * 5. 切「待裁决」真的带 `state` 参数去后端筛（不是前端切片）：两条请求
 *    `changed` + `unverifiable`，offset 回到 0。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const kyMock = vi.hoisted(() => ({ get: vi.fn() }))
vi.mock('@/lib/api', () => ({ createApiClient: () => kyMock }))

import { CaseVerifyCard } from './CaseVerifyCard'
import type { VerifyRunOut } from './api'

/**
 * ky 的 `get` 返回「可 await 且带 .json()」的 ResponsePromise，而 `./api` 里写的是
 * `.get(...).json<T>()` —— 桩只给 `.json()` 一个能力即可。
 */
function jsonOf<T>(data: T) {
  return { json: async () => data }
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

/** 一条核对记录：默认「检出问题」，一页无文本层，带一条红线 + 一条疑似 */
function runOf(over: Partial<VerifyRunOut> = {}): VerifyRunOut {
  return {
    id: 3,
    artifact_id: 9,
    case_id: 7,
    case_name: '张三诉李四借款纠纷',
    last_decision_action: '',
    last_decision_at: null,
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
    ],
    coverage: { pages_total: 10, pages_with_text: 9, pages_no_text: 1, text_compared: true },
    created_at: '2026-11-24T10:00:00+08:00',
    ...over,
  }
}

function pageOf(items: VerifyRunOut[], total = items.length) {
  return { total, items }
}

function renderCard(caseId = 7) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const utils = render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <CaseVerifyCard caseId={caseId} />
      </MemoryRouter>
    </QueryClientProvider>,
  )
  return { ...utils, queryClient }
}

/** 取第 n 次 `get('runs', ...)` 的查询参数（1 起算） */
function searchParamsOf(n: number): Record<string, unknown> {
  return (kyMock.get.mock.calls[n - 1]?.[1] as { searchParams: Record<string, unknown> }).searchParams
}

beforeEach(() => {
  vi.clearAllMocks()
  kyMock.get.mockReturnValue(jsonOf(pageOf([])))
})


describe('CaseVerifyCard：已处置的行', () => {
  it('标出「已采纳」，且不计入底部「待裁决」数', async () => {
    const decided = runOf({
      id: 91,
      state: 'changed',
      state_label: '疑似改动',
      last_decision_action: 'accept',
    })
    kyMock.get.mockReturnValue(jsonOf(pageOf([decided])))

    renderCard()

    expect(await screen.findByText('已采纳')).toBeTruthy()
    // 已采纳 = 已处置：不该再算进「还有 N 条要处理」
    expect(screen.queryByText(/条待裁决 → 去材料准备页处理/)).toBeNull()
  })
})

describe('CaseVerifyCard：空态', () => {
  it('没有核对记录时写「本案还没有核对记录」', async () => {
    const { container } = renderCard()

    expect(await screen.findByText('本案还没有核对记录')).toBeTruthy()
    // 历史按案件拉：case_id 必须带上；默认第一页 20 条、offset 0、不带 state
    expect(kyMock.get).toHaveBeenCalledWith(
      'runs',
      expect.objectContaining({ searchParams: { case_id: 7, limit: 20, offset: 0 } }),
    )
    container.remove()
  })
})

describe('CaseVerifyCard：记录渲染', () => {
  it('三条记录都渲染，覆盖率含「1 页无文本层，未核对」', async () => {
    kyMock.get.mockReturnValue(
      jsonOf(
        pageOf([
          runOf({ id: 3, doc_type: '起诉状' }),
          runOf({
            id: 2,
            doc_type: '证据目录',
            state: 'verified_clean',
            state_label: '核对无差异',
            coverage: { pages_total: 4, pages_with_text: 4, pages_no_text: 0 },
          }),
          runOf({
            id: 1,
            doc_type: '授权委托书',
            state: 'unverifiable',
            state_label: '无法核对',
            coverage: { pages_total: 2, pages_with_text: 0, pages_no_text: 2 },
          }),
        ]),
      ),
    )
    const { container } = renderCard()

    expect(await screen.findByText('起诉状')).toBeTruthy()
    expect(screen.getByText('证据目录')).toBeTruthy()
    expect(screen.getByText('授权委托书')).toBeTruthy()
    // 三行各自的状态文案原样显示
    expect(screen.getByText('检出问题')).toBeTruthy()
    expect(screen.getByText('核对无差异')).toBeTruthy()
    expect(screen.getByText('无法核对')).toBeTruthy()
    // pages_no_text > 0 必须说出来：那几页比对根本没看到内容
    expect(screen.getByText('覆盖率 9/10 页 · 1 页无文本层，未核对')).toBeTruthy()
    expect(screen.getByText('覆盖率 0/2 页 · 2 页无文本层，未核对')).toBeTruthy()
    // 全页都有文本层时不写多余的「N 页无文本层」
    expect(screen.getByText('覆盖率 4/4 页')).toBeTruthy()
    // 全部一页装得下，底部不再显示「加载更多」
    expect(screen.queryByRole('button', { name: '加载更多' })).toBeNull()
    container.remove()
  })

  it('发现项渲染红/黄徽标与 expected → actual', async () => {
    kyMock.get.mockReturnValue(jsonOf(pageOf([runOf()])))
    const { container } = renderCard()

    await screen.findByText('起诉状')
    const body = within(document.body)
    expect(body.getByText('红线')).toBeTruthy()
    expect(body.getByText('借款金额被改')).toBeTruthy()
    expect(body.getByText('100000 → 120000')).toBeTruthy()
    expect(body.getByText('疑似')).toBeTruthy()
    expect(body.getByText('诉请第二项缺失')).toBeTruthy()
    // expected 有、actual 空 → 空的一侧写成「（空）」，不留一个没有下文的箭头
    expect(body.getByText('第二项存在 → （空）')).toBeTruthy()
    container.remove()
  })

  it('底部提示指向材料准备页（本卡不提供上传/发起核对）', async () => {
    kyMock.get.mockReturnValue(jsonOf(pageOf([runOf()])))
    const { container } = renderCard()

    const link = await screen.findByRole('link', { name: /有 1 条待裁决 → 去材料准备页处理/ })
    expect(link.getAttribute('href')).toBe('/material-prep')
    expect(screen.getByText('上传回传件、发起核对在材料准备页')).toBeTruthy()
    container.remove()
  })
})

describe('CaseVerifyCard：分页', () => {
  it('「加载更多」用 offset 递增发起第二页请求，并把新记录接在后面', async () => {
    const first = Array.from({ length: 3 }, (_, i) => runOf({ id: 30 - i, doc_type: `文书${i + 1}` }))
    kyMock.get.mockImplementation((_path: string, options: { searchParams: { offset: number } }) =>
      options.searchParams.offset === 0
        ? jsonOf(pageOf(first, 25))
        : jsonOf(pageOf([runOf({ id: 4, doc_type: '第 21 条' })], 25)),
    )
    const { container } = renderCard()

    await screen.findByText('文书1')
    // 首屏：offset 0 / limit 20
    expect(searchParamsOf(1)).toMatchObject({ case_id: 7, limit: 20, offset: 0 })

    fireEvent.click(screen.getByRole('button', { name: '加载更多' }))

    expect(await screen.findByText('第 21 条')).toBeTruthy()
    // 第二页真的是 offset 20（不是把首屏再拉一遍）
    expect(searchParamsOf(2)).toMatchObject({ case_id: 7, limit: 20, offset: 20 })
    container.remove()
  })
})

describe('CaseVerifyCard：状态筛选', () => {
  it('切「待裁决」：两次请求带 state=changed / state=unverifiable，offset 回到 0', async () => {
    kyMock.get.mockReturnValue(jsonOf(pageOf([])))
    const { container } = renderCard()

    await screen.findByText('本案还没有核对记录')
    fireEvent.click(screen.getByRole('button', { name: '待裁决' }))

    // 服务端筛选：两个阻塞状态各发一条，offset 从 0 起
    expect(await screen.findByText('这一档没有核对记录')).toBeTruthy()
    expect(kyMock.get).toHaveBeenCalledWith(
      'runs',
      expect.objectContaining({
        searchParams: { case_id: 7, state: 'changed', limit: 20, offset: 0 },
      }),
    )
    expect(kyMock.get).toHaveBeenCalledWith(
      'runs',
      expect.objectContaining({
        searchParams: { case_id: 7, state: 'unverifiable', limit: 20, offset: 0 },
      }),
    )
    container.remove()
  })

  it('切「已通过」：带 state=identical / state=verified_clean', async () => {
    kyMock.get.mockReturnValue(jsonOf(pageOf([])))
    const { container } = renderCard()

    await screen.findByText('本案还没有核对记录')
    fireEvent.click(screen.getByRole('button', { name: '已通过' }))

    await screen.findByText('这一档没有核对记录')
    expect(kyMock.get).toHaveBeenCalledWith(
      'runs',
      expect.objectContaining({ searchParams: { case_id: 7, state: 'identical', limit: 20, offset: 0 } }),
    )
    expect(kyMock.get).toHaveBeenCalledWith(
      'runs',
      expect.objectContaining({ searchParams: { case_id: 7, state: 'verified_clean', limit: 20, offset: 0 } }),
    )
    container.remove()
  })
})
