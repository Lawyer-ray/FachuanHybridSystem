// @vitest-environment jsdom
/**
 * 审批面板测试（jsdom）。守的是三条**会让人做错决定**的判据：
 *
 * 1. **入口只认服务端能力位**：`can_review && review_status==='pending'` 才出现「审核」，
 *    同样待审但没有 `can_review` 的条目一个按钮都不给（前端不判 is_admin）；
 * 2. **diff 用语义标签**：新增行必须是 `<ins>`、删除行必须是 `<del>`——用色块假装
 *    diff 会让屏幕阅读器与复制粘贴读不出「哪行是新的」；
 * 3. **驳回必须写理由**：空备注先在本地拦下、不发请求（否则作者只能盲改）；
 * 4. **「全所确认」不能默认逼每个人勾**：第一次通过不带 `acknowledged_firm_wide`，
 *    只有收到 422 且文案提到「全所」时才亮出勾选框，勾了再提交才成功。
 *
 * 渲染整只抽屉（而不是单独渲染面板）是刻意的：入口条件的判据在 `SkillRow` 上，
 * 单独渲染面板测不到「什么时候该有那个按钮」。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { HTTPError } from 'ky'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  fetchAgentSkills: vi.fn(),
  fetchAgentSkill: vi.fn(),
  fetchAgentSkillQuota: vi.fn(),
  fetchAgentSkillDiff: vi.fn(),
  validateAgentSkill: vi.fn(),
  reviewAgentSkill: vi.fn(),
  createAgentSkill: vi.fn(),
  updateAgentSkill: vi.fn(),
  deleteAgentSkill: vi.fn(),
  setAgentSkillEnabled: vi.fn(),
  duplicateAgentSkill: vi.fn(),
}))
vi.mock('../../skill-api', () => apiMock)

const toastStubs = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn(), info: vi.fn(), warning: vi.fn() }))
vi.mock('sonner', () => ({ toast: toastStubs }))

import { useSkillDrawer } from '../../skill-drawer'
import type { AgentSkill } from '../../types'
import { SkillDrawer } from './SkillDrawer'

/** 一条所内技能的基础形状（缺省：已生效、无可审内容） */
function firmSkill(overrides: Partial<AgentSkill> = {}): AgentSkill {
  return {
    key: 'skill:firm-1',
    name: 'contract-review',
    title: '所内合同审查',
    description: '所内统一的合同审查口径',
    enabled: true,
    source: 'law_firm',
    scope: 'law_firm',
    scope_weight: 2,
    editable: true,
    version: 3,
    status: 'active',
    review_status: 'none',
    review_note: '',
    published_version: 2,
    has_unpublished_changes: false,
    shadowed: [],
    effective: true,
    shadowed_by: null,
    can_edit: true,
    can_submit: false,
    can_review: false,
    can_archive: false,
    can_restore: false,
    ...overrides,
  }
}

/** 待审且有审批权的条目：列表里的「审核」入口就该出现 */
const REVIEWABLE = firmSkill({ key: 'skill:firm-1', review_status: 'pending', has_unpublished_changes: true, can_review: true })

/** 同样待审、但服务端没给审批权：不该出现「审核」 */
const NOT_REVIEWABLE = firmSkill({
  key: 'skill:firm-2',
  name: 'firm-checklist',
  title: '所内核对清单',
  review_status: 'pending',
  can_review: false,
})

function quota() {
  return {
    max_skills: 20,
    used: 2,
    by_scope: { lawyer: 1, team: 0, law_firm: 2 },
    // 共享层上限给 0：旧后端口径，不显示该层配额条（与本组判据无关）
    max_by_scope: { lawyer: 20, team: 0, law_firm: 0 },
    can_create_firm: false,
  }
}

function renderDrawer() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })
  const wrap = ({ children }: { children: ReactNode }) => <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  return render(<SkillDrawer />, { wrapper: wrap })
}

/** ky v2 在真实往返里把响应体预解析进 `error.data`；这里按同一形状造一个 422 */
function httpError(status: number, body: unknown): HTTPError {
  const error = new HTTPError(
    new Response(null, { status }),
    new Request('http://localhost/api/v1/agent/skills/skill%3Afirm-1/review'),
    {} as never,
  )
  error.data = body
  return error
}

/** 打开「所内」tab 并点进第一条待审条目的审核面板 */
async function openReviewPanel() {
  renderDrawer()
  fireEvent.click(await screen.findByRole('tab', { name: '所内' }))
  fireEvent.click(await screen.findByRole('button', { name: '审核 所内合同审查' }))
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  useSkillDrawer.setState({ open: true })
  apiMock.fetchAgentSkills.mockResolvedValue({ skills: [REVIEWABLE, NOT_REVIEWABLE] })
  apiMock.fetchAgentSkillQuota.mockResolvedValue(quota())
  apiMock.fetchAgentSkill.mockResolvedValue({ ...REVIEWABLE, body: '1. 主体\n2. 标的' })
  apiMock.validateAgentSkill.mockResolvedValue({ ok: true, errors: [], preview: '', safety: [] })
  apiMock.fetchAgentSkillDiff.mockResolvedValue({
    v1: 2,
    v2: 3,
    hunks: [
      { op: 'equal', lines: ['1. 主体', '2. 标的'] },
      { op: 'del', lines: ['3. 送达期限 15 日'] },
      { op: 'ins', lines: ['3. 送达期限 30 日'] },
    ],
  })
  apiMock.reviewAgentSkill.mockResolvedValue({ ...REVIEWABLE, review_status: 'none', body: '' })
})

describe('SkillReviewPanel：入口判据', () => {
  it('待审且 can_review 才有「审核」；同样待审但没权限的条目不给入口', async () => {
    renderDrawer()
    fireEvent.click(await screen.findByRole('tab', { name: '所内' }))

    // 有待审条目的那一行有入口，另一行没有
    expect(await screen.findByRole('button', { name: '审核 所内合同审查' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: '审核 所内核对清单' })).toBeNull()
  })

  it('diff 用 <ins> / <del> 语义标签渲染改动行', async () => {
    await openReviewPanel()

    await waitFor(() => expect(document.querySelector('del')).toBeTruthy())
    expect(document.querySelector('del')?.textContent).toContain('3. 送达期限 15 日')
    expect(document.querySelector('ins')?.textContent).toContain('3. 送达期限 30 日')
  })
})

describe('SkillReviewPanel：驳回', () => {
  it('空备注被本地拦下：不发审批请求，理由框下方报字段级错误', async () => {
    await openReviewPanel()

    fireEvent.click(await screen.findByRole('button', { name: '驳回' }))
    expect(await screen.findByText(/驳回理由必填/)).toBeTruthy()
    expect(apiMock.reviewAgentSkill).not.toHaveBeenCalled()
  })
})

describe('SkillReviewPanel：通过', () => {
  it('第一次不带全所确认；422 提到「全所」后才亮勾选框，勾了再提交成功', async () => {
    apiMock.reviewAgentSkill
      .mockRejectedValueOnce(httpError(422, { detail: 'acknowledged_firm_wide: 全所生效的指令需要先确认影响范围后再发布' }))
      .mockResolvedValueOnce({ ...REVIEWABLE, review_status: 'none', body: '' })
    await openReviewPanel()

    fireEvent.click(await screen.findByRole('button', { name: '通过' }))
    expect(await screen.findByText(/全所生效的指令需要先确认影响范围/)).toBeTruthy()
    // 服务端要求之前不带该字段：默认逼每个人勾选会把确认变成盲点
    expect(apiMock.reviewAgentSkill.mock.calls[0]?.[1]).not.toHaveProperty('acknowledged_firm_wide')

    fireEvent.click(screen.getByRole('checkbox', { name: /我已确认这条指令在全所范围内成立/ }))
    fireEvent.click(screen.getByRole('button', { name: '通过' }))

    await waitFor(() => expect(apiMock.reviewAgentSkill).toHaveBeenCalledTimes(2))
    expect(apiMock.reviewAgentSkill.mock.calls[1]?.[1]).toEqual({ decision: 'approve', acknowledged_firm_wide: true })
    // 审批成功回到列表（tab 栏重新出现），不是停在面板上
    expect(await screen.findByRole('tab', { name: '所内' })).toBeTruthy()
  })
})
