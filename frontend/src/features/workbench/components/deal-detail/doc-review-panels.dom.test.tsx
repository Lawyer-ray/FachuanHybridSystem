// @vitest-environment jsdom
/**
 * 风险清单 / 版本历史两个右栏面板的交互契约。
 *
 * 这里守的都是**不可撤销或会改文件**的动作：
 * 1. 采纳 = 真的写文件，所以必须真的调后端（不能只改本地状态）；
 * 2. 批量采纳 = 一次写几十条，**必须二次确认**；
 * 3. 驳回必须选理由码（自由文本统计不出误报率）；
 * 4. 锚点失效的条目必须显示出来且不能悄悄采纳（文件不会动，律师得知道）；
 * 5. 清单条目 → 画布定位（`onLocate`）、画布选区 → 条目高亮，缺任一半，
 *    「左看文档右看清单」就还是割裂的；
 * 6. 回滚也要二次确认，并说明「可以再滚回来」；
 * 7. 另两个维度不能丢：强制性违规要点名标红，阶段分组连 0 条的阶段也要列出
 *    （那是「该阶段查过了」的覆盖证明），结论要能溯源到风险来源。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  fetchLatestRun: vi.fn(),
  startReview: vi.fn(),
  decideFinding: vi.fn(),
  bulkAccept: vi.fn(),
  listSnapshots: vi.fn(),
  restoreSnapshot: vi.fn(),
  fetchRun: vi.fn(),
  fetchReport: vi.fn(),
}))

vi.mock('./doc-review-api', async (orig) => {
  const actual = await orig<typeof import('./doc-review-api')>()
  return { ...actual, ...api }
})

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() }))
vi.mock('sonner', () => ({ toast }))

import { ReviewPanel } from './ReviewPanel'
import { VersionHistoryPanel } from './VersionHistoryPanel'
import type { FindingItem, ReviewRunPayload, SnapshotItem } from './doc-review-api'

function finding(over: Partial<FindingItem> = {}): FindingItem {
  return {
    id: 1,
    ordinal: 0,
    verdict: 'deviation',
    severity: 'high',
    kind: 'risk',
    clause_type: '违约责任',
    rule_key: 'breach.liquidated_damages_cap',
    legal_basis: '《民法典》第585条',
    quote: '',
    title: '违约金无上限',
    reason: '可能被判赔超过实际损失',
    suggestion_original: '甲方愿意支付人民币壹万元整。',
    suggestion_replacement: '甲方同意支付，违约金以总价款 20% 为限。',
    suggestion_note: '',
    delivery: 'revision',
    status: 'proposed',
    reject_reason_code: '',
    reject_note: '',
    docx_rev_ids: [],
    comment_ids: [],
    ...over,
  }
}

function run(over: Partial<ReviewRunPayload> = {}): ReviewRunPayload {
  return {
    id: 7,
    owner_kind: 'contract',
    owner_id: 393,
    subpath: '1-合同/a.docx',
    stance: 'neutral',
    contract_type: '',
    status: 'done',
    playbook_key: 'builtin:general:neutral',
    playbook_version: 1,
    summary: {},
    error_message: '',
    created_at: new Date().toISOString(),
    finished_at: new Date().toISOString(),
    findings: [],
    ...over,
  }
}

function withQuery(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={qc}>{node}</QueryClientProvider>
}

beforeEach(() => {
  vi.clearAllMocks()
  api.fetchLatestRun.mockResolvedValue(run())
  api.listSnapshots.mockResolvedValue({ items: [] })
  api.decideFinding.mockResolvedValue({ ok: true, status: 'accepted', reason: '', stale: false, rev_ids: [1], comment_ids: [] })
  api.bulkAccept.mockResolvedValue({ accepted: 2, stale: 0, failed: 0, details: [] })
})

describe('ReviewPanel', () => {
  it('把结论按严重度分组，并显示待决条数', async () => {
    api.fetchLatestRun.mockResolvedValue(
      run({ findings: [finding({ id: 1 }), finding({ id: 2, severity: 'low', title: '措辞建议' })] }),
    )
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={vi.fn()} />))

    expect(await screen.findByText('违约金无上限')).toBeTruthy()
    expect(screen.getByText('2 待决')).toBeTruthy()
    expect(screen.getByText('高危')).toBeTruthy()
    expect(screen.getByText('低危')).toBeTruthy()
  })

  it('强制性违规点名标出「强制性」角标', async () => {
    api.fetchLatestRun.mockResolvedValue(run({ findings: [finding({ rule_class: 'mandatory' })] }))
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={vi.fn()} />))

    expect(await screen.findByText('强制性')).toBeTruthy()
  })

  it('强制性条目同时显示后果档位（「可能无效」不等于「违约」，不能混着显示）', async () => {
    api.fetchLatestRun.mockResolvedValue(
      run({ findings: [finding({ rule_class: 'mandatory', consequence: 'invalid' })] }),
    )
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={vi.fn()} />))

    // 角标是「强制性·可能无效」
    expect(await screen.findByText(/强制性·可能无效/)).toBeTruthy()
  })

  it('后果是「违约责任」时不额外标注（默认不打扰）', async () => {
    api.fetchLatestRun.mockResolvedValue(run({ findings: [finding({ rule_class: 'mandatory', consequence: 'breach' })] }))
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={vi.fn()} />))

    expect(await screen.findByText('强制性')).toBeTruthy()
    expect(screen.queryByText(/·违约责任/)).toBeNull()
  })

  it('结论标出风险来源；辅助来源弱化显示并标「（辅）」', async () => {
    api.fetchLatestRun.mockResolvedValue(
      run({
        findings: [
          finding({ id: 1, risk_source: 'statute' }),
          finding({
            id: 2,
            severity: 'low',
            title: '受让方资质需补充',
            risk_source: 'scenario',
            source_weight: 'supporting',
          }),
        ],
      }),
    )
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={vi.fn()} />))

    expect(await screen.findByText('据：法律规定')).toBeTruthy()
    expect(screen.getByText('据：场景推演（辅）')).toBeTruthy()
  })

  it('切到「阶段」分组后四个阶段头都在，0 条的阶段也列出来（覆盖证明）', async () => {
    api.fetchLatestRun.mockResolvedValue(
      run({
        findings: [
          finding({ id: 1, stage: 'before' }),
          finding({ id: 2, severity: 'medium', stage: 'during', title: '付款节奏不明' }),
          finding({ id: 3, severity: 'low', stage: 'general', title: '措辞建议' }),
        ],
      }),
    )
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={vi.fn()} />))

    expect(await screen.findByText('违约金无上限')).toBeTruthy()
    expect(screen.getByRole('tab', { name: '严重度' }).getAttribute('aria-selected')).toBe('true')

    fireEvent.click(screen.getByRole('tab', { name: '阶段' }))

    for (const head of ['转让前', '转让中', '转让后', '通用']) {
      expect(screen.getByText(head)).toBeTruthy()
    }
    expect(screen.getAllByText('1 条')).toHaveLength(3)
    expect(screen.getAllByText('0 条')).toHaveLength(1)
    expect(screen.getByText('本阶段无结论')).toBeTruthy()
  })

  it('点条目把原文送进画布定位', async () => {
    const onLocate = vi.fn()
    api.fetchLatestRun.mockResolvedValue(run({ findings: [finding()] }))
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={onLocate} />))

    fireEvent.click(await screen.findByText('违约金无上限'))
    expect(onLocate).toHaveBeenCalledWith(expect.objectContaining({ id: 1 }))
  })

  it('采纳会真的调后端（写文件不可只改本地状态）', async () => {
    api.fetchLatestRun.mockResolvedValue(run({ findings: [finding()] }))
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={vi.fn()} />))

    fireEvent.click(await screen.findByRole('button', { name: /^采纳$/ }))
    await waitFor(() => expect(api.decideFinding).toHaveBeenCalledWith(1, 'accept', { reasonCode: undefined, note: undefined }))
  })

  it('锚点失效的结论显式标出「原文已变」', async () => {
    api.fetchLatestRun.mockResolvedValue(run({ findings: [finding({ status: 'stale' })] }))
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={vi.fn()} />))

    expect(await screen.findByText('原文已变')).toBeTruthy()
    expect(screen.getByText('锚点失效')).toBeTruthy()
  })

  it('驳回必须先选理由码，且理由码随请求发出', async () => {
    api.fetchLatestRun.mockResolvedValue(run({ findings: [finding()] }))
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={vi.fn()} />))

    fireEvent.click(await screen.findByRole('button', { name: /驳回/ }))
    const select = await screen.findByLabelText('驳回理由')
    fireEvent.change(select, { target: { value: 'false_positive' } })
    fireEvent.click(screen.getByRole('button', { name: '确认驳回' }))

    await waitFor(() =>
      expect(api.decideFinding).toHaveBeenCalledWith(1, 'reject', { reasonCode: 'false_positive', note: '' }),
    )
  })

  it('批量采纳必须二次确认：点「全部采纳」只开弹窗，确认后才调接口', async () => {
    api.fetchLatestRun.mockResolvedValue(run({ findings: [finding()] }))
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={vi.fn()} />))

    fireEvent.click(await screen.findByRole('button', { name: '全部采纳' }))
    expect(api.bulkAccept).not.toHaveBeenCalled()
    expect(await screen.findByText(/不可撤销/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '确认写入文件' }))
    await waitFor(() => expect(api.bulkAccept).toHaveBeenCalledWith(7, { severity: 'high' }))
  })

  it('画布选区命中清单条目时高亮出来（双向定位的另一半）', async () => {
    api.fetchLatestRun.mockResolvedValue(run({ findings: [finding()] }))
    render(
      withQuery(
        <ReviewPanel
          kind="contract"
          ownerId={393}
          subpath="1-合同/a.docx"
          selection="甲方愿意支付人民币壹万元整。"
          onLocate={vi.fn()}
        />,
      ),
    )

    expect(await screen.findByText(/画布选区命中了清单条目/)).toBeTruthy()
  })

  it('锚点失效时给出「文件未改动」的明确提示，而不是静默', async () => {
    api.fetchLatestRun.mockResolvedValue(run({ findings: [finding()] }))
    api.decideFinding.mockResolvedValue({
      ok: false,
      status: 'stale',
      reason: '未在文档中找到该原文片段',
      stale: true,
      rev_ids: [],
      comment_ids: [],
    })
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={vi.fn()} />))

    fireEvent.click(await screen.findByRole('button', { name: /^采纳$/ }))
    await waitFor(() => expect(toast.warning).toHaveBeenCalled())
    expect(String(toast.warning.mock.calls[0]?.[0])).toContain('未改动文件')
  })

  it('还没审过时给出可执行的说法，而不是空白', async () => {
    api.fetchLatestRun.mockResolvedValue(run({ status: 'none', findings: [] }))
    render(withQuery(<ReviewPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" selection="" onLocate={vi.fn()} />))

    expect(await screen.findByText('这份文件还没审查过')).toBeTruthy()
    expect(screen.getByText(/不产生第二份文档/)).toBeTruthy()
  })
})

describe('VersionHistoryPanel', () => {
  const snap = (seq: number, reason = 'editor_save'): SnapshotItem => ({
    seq,
    sha256: 'a'.repeat(64),
    size: 2048,
    reason,
    actor_kind: 'human',
    actor_id: 1,
    created_at: new Date().toISOString(),
  })

  it('列出版本并标出「上一版」', async () => {
    api.listSnapshots.mockResolvedValue({ items: [snap(3), snap(2, 'ai_rewrite')] })
    render(withQuery(<VersionHistoryPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" />))

    expect(await screen.findByText('v3')).toBeTruthy()
    expect(screen.getByText('v2')).toBeTruthy()
    expect(screen.getByText('上一版')).toBeTruthy()
    expect(screen.getByText('编辑器保存')).toBeTruthy()
    expect(screen.getByText('AI 改写')).toBeTruthy()
  })

  it('回滚要二次确认，并说明这次回滚可以再滚回来', async () => {
    api.listSnapshots.mockResolvedValue({ items: [snap(2)] })
    api.restoreSnapshot.mockResolvedValue({ restored: true, reason: '', seq: 2, sha256: 'a', previous_seq: 3 })
    render(withQuery(<VersionHistoryPanel kind="contract" ownerId={393} subpath="1-合同/a.docx" />))

    fireEvent.click(await screen.findByRole('button', { name: /回到这一版/ }))
    expect(api.restoreSnapshot).not.toHaveBeenCalled()
    expect(await screen.findByText(/可以再滚回来/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '确认回滚' }))
    await waitFor(() => expect(api.restoreSnapshot).toHaveBeenCalledWith('contract', 393, '1-合同/a.docx', 2))
  })
})
