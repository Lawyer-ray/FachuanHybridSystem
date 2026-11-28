// @vitest-environment jsdom
/**
 * 试跑面板测试（jsdom）。守的是**审批人会因此做错判断**的那几条：
 *
 * 1. **三档模式必须自报「验的是哪一层」**：`index` 档对未发布的技能要禁用并说明原因——
 *    否则审批人会在一条待审稿上点「真索引」，拿到一个「模型没去读」的答案，
 *    误判成「技能写得不好」；
 * 2. **等待态必须存在**：这是 3–45 秒的慢端点，没有等待态就等于让律师对着一个
 *    没反应的按钮反复点，反复烧额度；
 * 3. **取消要真的断开**（AbortSignal 传到请求上），不是只把界面切回去；
 * 4. **`model` 为空时整项不渲染**：渲染成 `null` 会让人以为模型坏了；
 * 5. **`tool_errors` 必须带那句后果**：「回复可能不是技能的效果」——少了它，一次
 *    「模型没能读到全文」会被读成「这条技能没效果」，结论正好反过来；
 * 6. **额度为 0 时按钮禁用 + 说清恢复时间**，而不是让人点了再吃 429。
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import type { ReactNode } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  runAgentSkillTrial: vi.fn(),
  fetchAgentSkillTrialQuota: vi.fn(),
}))
// 面板从 `../../skill-api` 的 re-export 取这两个函数（试跑域实体在 skill-trial-api.ts）
vi.mock('../../skill-api', () => apiMock)

import type { AgentSkill } from '../../types'
import type { AgentSkillTrialResult } from '../../skill-types'
import { SkillTrialPanel } from './SkillTrialPanel'

function skill(overrides: Partial<AgentSkill> = {}): AgentSkill {
  return {
    key: 'skill:trial-1',
    name: 'contract-review',
    title: '合同审查三段式',
    description: '审阅合同时使用',
    enabled: true,
    source: 'law_firm',
    scope: 'law_firm',
    scope_weight: 2,
    editable: true,
    version: 3,
    status: 'active',
    review_status: 'pending',
    review_note: '',
    published_version: 2,
    has_unpublished_changes: true,
    shadowed: [],
    effective: false,
    shadowed_by: null,
    can_edit: true,
    can_submit: false,
    can_review: true,
    can_archive: true,
    can_restore: false,
    can_promote: false,
    ...overrides,
  }
}

function trialResult(overrides: Partial<AgentSkillTrialResult> = {}): AgentSkillTrialResult {
  return {
    ok: true,
    text: '先输出结论，再列争点。',
    backend: 'pi',
    model: 'kimi-2.6',
    duration_ms: 2722,
    skill_key: 'skill:trial-1',
    skill_name: 'contract-review',
    skill_scope: 'law_firm',
    skill_version: 3,
    injected: '<skill name="contract-review">…</skill>',
    tool_calls: [],
    error: '',
    mode: 'index',
    tool_errors: [],
    trial_id: 't-1',
    ...overrides,
  }
}

function renderPanel(element: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>)
}

beforeEach(() => {
  apiMock.runAgentSkillTrial.mockReset()
  apiMock.fetchAgentSkillTrialQuota.mockReset()
  apiMock.fetchAgentSkillTrialQuota.mockResolvedValue({ limit: 30, used: 4, remaining: 26 })
})

describe('试跑模式', () => {
  it('三档都自报验的是哪一层', async () => {
    renderPanel(<SkillTrialPanel skill={skill()} />)
    expect(await screen.findByText('内联全文（验指令语义）')).toBeTruthy()
    expect(screen.getByText(/验的是这条指令写得好不好/)).toBeTruthy()
    expect(screen.getByText(/模型必须自己调/)).toBeTruthy()
  })

  it('未发布的技能禁用真索引档并说明原因', async () => {
    renderPanel(<SkillTrialPanel skill={skill({ status: 'draft' })} />)
    const indexOption = await screen.findByRole('radio', { name: /真索引/ })
    expect((indexOption as HTMLButtonElement).disabled).toBe(true)
    expect(screen.getByText(/先发布才能验证自主发现/)).toBeTruthy()
  })
})

describe('等待态与取消', () => {
  it('运行后出现等待态，取消真的断开请求', async () => {
    let captured: AbortSignal | undefined
    apiMock.runAgentSkillTrial.mockImplementation(
      (_key: string, _input: unknown, signal?: AbortSignal) =>
        new Promise((_resolve, reject) => {
          captured = signal
          signal?.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))
        }),
    )
    renderPanel(<SkillTrialPanel skill={skill()} />)
    fireEvent.click(await screen.findByRole('button', { name: '运行试跑' }))

    expect(await screen.findByRole('status')).toBeTruthy()
    expect(screen.getByText(/模型正在读你的技能/)).toBeTruthy()

    fireEvent.click(screen.getByRole('button', { name: '取消' }))
    expect(captured?.aborted).toBe(true)
    expect(await screen.findByText(/已取消这次试跑/)).toBeTruthy()
  })
})

describe('结果判读', () => {
  it('model 为空时整项不渲染（不显示 null）', async () => {
    apiMock.runAgentSkillTrial.mockResolvedValue(trialResult({ model: null }))
    const { container } = renderPanel(<SkillTrialPanel skill={skill()} />)
    fireEvent.click(await screen.findByRole('button', { name: '运行试跑' }))

    expect(await screen.findByText('先输出结论，再列争点。')).toBeTruthy()
    expect(container.textContent).not.toContain('null')
    // 其它元信息仍在：模型名缺失不该把整行吞掉
    expect(container.textContent).toContain('pi')
  })

  it('工具失败要带「回复可能不是技能的效果」这句后果', async () => {
    apiMock.runAgentSkillTrial.mockResolvedValue(
      trialResult({
        tool_calls: ['mcp__fachuan__get_agent_skill'],
        tool_errors: [{ tool: 'mcp__fachuan__get_agent_skill', message: '未发布：这条技能还在审批中' }],
      }),
    )
    renderPanel(<SkillTrialPanel skill={skill()} />)
    fireEvent.click(await screen.findByRole('button', { name: '运行试跑' }))

    expect(await screen.findByText(/模型试图调用 get_agent_skill 但失败/)).toBeTruthy()
    expect(screen.getByText(/回复可能不是技能的效果/)).toBeTruthy()
  })
})

describe('额度', () => {
  it('额度为 0 时禁用按钮并说清恢复时间', async () => {
    apiMock.fetchAgentSkillTrialQuota.mockResolvedValue({
      limit: 30,
      used: 30,
      remaining: 0,
      reset_at: '2026-11-29T00:00:00+08:00',
    })
    renderPanel(<SkillTrialPanel skill={skill()} />)

    const button = await screen.findByRole('button', { name: '运行试跑' })
    await waitFor(() => expect((button as HTMLButtonElement).disabled).toBe(true))
    expect(screen.getByText(/今日额度已用完/)).toBeTruthy()
  })

  it('额度取不到时不误禁用（「不知道」不等于「用完了」）', async () => {
    apiMock.fetchAgentSkillTrialQuota.mockRejectedValue(new Error('404'))
    renderPanel(<SkillTrialPanel skill={skill()} />)

    const button = await screen.findByRole('button', { name: '运行试跑' })
    await waitFor(() => expect(screen.getByText(/今日额度取不到（不影响试跑）/)).toBeTruthy())
    expect((button as HTMLButtonElement).disabled).toBe(false)
  })
})
