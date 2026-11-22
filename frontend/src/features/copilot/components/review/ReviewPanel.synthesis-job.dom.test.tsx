// @vitest-environment jsdom
/**
 * 综合结论后台任务（jsdom）：阶段进度 / 取消 / 刷新恢复 / 终态渲染 / 卸载只停轮询。
 *
 * 锁的是评审 🔴5 的修复：综合不再是一个会被超时掐断的同步请求，而是「提交任务 → 轮询」。
 * - 运行中按钮显示阶段，旁边有「取消」；取消走后端接口，终态由轮询收口；
 * - 刷新页面（重新挂载）时该轮还在跑 → 接着显示进度，不重新提交（不重复花钱）；
 * - 组件卸载只停止轮询，**不**取消后台任务；
 * - 已结束的历史任务不重复弹失败提示。
 */

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const apiSpies = vi.hoisted(() => ({
  fetchReview: vi.fn(),
  fetchReviewOptions: vi.fn(),
  fetchSynthesis: vi.fn(),
}))
vi.mock('../../api', async () => {
  const actual = await vi.importActual<typeof import('../../api')>('../../api')
  return { ...actual, ...apiSpies }
})

const jobSpies = vi.hoisted(() => ({
  startSynthesisJob: vi.fn(),
  fetchLatestSynthesisJob: vi.fn(),
  cancelSynthesisJob: vi.fn(),
  waitForSynthesisJob: vi.fn(),
}))
vi.mock('../../review-api', async () => {
  const actual = await vi.importActual<typeof import('../../review-api')>('../../review-api')
  return { ...actual, ...jobSpies }
})

const toastMock = vi.hoisted(() => Object.assign(vi.fn(), { error: vi.fn() }))
vi.mock('sonner', () => ({ toast: toastMock }))

import type { SynthesisJob } from '../../adjudication-types'
import type { AgentBackendOption } from '../../types'
import { useCopilot } from '../../store'
import { ReviewPanel } from './ReviewPanel'

const AGENTS = ['pi', 'dsh'] as const
const TARGET = { sessionId: 's-1', turn: 2 }

function job(over: Partial<SynthesisJob> = {}): SynthesisJob {
  return {
    job_id: 'job-1',
    session_id: 's-1',
    turn: 2,
    status: 'running',
    stage: 'synthesis',
    error: '',
    cancel_requested: false,
    review: true,
    created: true,
    created_at: '2026-11-22T00:00:00Z',
    updated_at: '2026-11-22T00:00:00Z',
    synthesis: null,
    ...over,
  }
}

const synthesis = {
  synthesis_id: 'syn-1',
  session_id: 's-1',
  turn: 2,
  text: '综合稿正文[来源：pi]',
  model: 'kimi-2.6',
  lanes_used: ['pi', 'dsh'],
  dropped: [],
  citations: [],
  unverified: [],
  tokens: {},
}

interface PollOptions {
  onUpdate?: (value: SynthesisJob) => void
  signal?: AbortSignal
}

/** 可由用例手动推进的轮询：记录 onUpdate / signal，返回一个由用例 resolve 的 Promise。 */
function controllablePoll() {
  const state: { resolve: (value: SynthesisJob) => void } & PollOptions = { resolve: () => undefined }
  jobSpies.waitForSynthesisJob.mockImplementation(
    (_sessionId: string, _job: SynthesisJob, options: PollOptions) =>
      new Promise<SynthesisJob>((resolve) => {
        state.resolve = resolve
        state.onUpdate = options.onUpdate
        state.signal = options.signal
      }),
  )
  return state
}

beforeEach(() => {
  vi.clearAllMocks()
  apiSpies.fetchReview.mockRejectedValue(new Error('404'))
  apiSpies.fetchSynthesis.mockRejectedValue(new Error('404'))
  apiSpies.fetchReviewOptions.mockResolvedValue({ rubric_ids: [], judge_models: ['judge-a'], max_lanes: 5 })
  jobSpies.fetchLatestSynthesisJob.mockRejectedValue(new Error('404'))
})

afterEach(() => {
  cleanup()
  useCopilot.setState({ backends: [] })
})

function backend(kind: string, models: string[]): AgentBackendOption {
  return { kind, label: kind, description: '', available: true, reason: '', capabilities: {}, models }
}

describe('综合结论后台任务', () => {
  it('「执行」下拉排掉不支持隔离运行的 dsh，pi 总在', async () => {
    render(<ReviewPanel target={TARGET} agents={AGENTS} />)
    const select = (await screen.findByTestId('synthesis-kind')) as HTMLSelectElement
    const values = Array.from(select.options).map((option) => option.value)
    expect(values).toContain('pi')
    expect(values).not.toContain('dsh')
  })

  it('提交后显示阶段进度与「取消」；点取消走后端接口，终态由轮询收口', async () => {
    const poll = controllablePoll()
    jobSpies.startSynthesisJob.mockResolvedValue(job({ status: 'queued', stage: '' }))
    jobSpies.cancelSynthesisJob.mockResolvedValue(job({ cancel_requested: true }))
    render(<ReviewPanel target={TARGET} agents={AGENTS} />)

    fireEvent.click(await screen.findByRole('button', { name: /生成综合结论/ }))
    await waitFor(() => expect(screen.getByTestId('synthesis-run').textContent).toContain('排队中'))

    // 后台推进到核验阶段：按钮跟着显示
    act(() => poll.onUpdate?.(job({ stage: 'verify' })))
    expect(screen.getByTestId('synthesis-run').textContent).toContain('核验引用中')

    fireEvent.click(screen.getByTestId('synthesis-cancel'))
    await waitFor(() => expect(jobSpies.cancelSynthesisJob).toHaveBeenCalledWith('s-1', 'job-1'))
    await waitFor(() => expect(screen.getByTestId('synthesis-run').textContent).toContain('正在取消'))

    await act(async () => poll.resolve(job({ status: 'cancelled', stage: '' })))
    expect(toastMock).toHaveBeenCalledWith('已取消综合结论')
    await waitFor(() => expect(screen.getByTestId('synthesis-run').textContent).toContain('生成综合结论'))
    expect(screen.queryByTestId('synthesis-cancel')).toBeNull()
    expect(screen.queryByTestId('synthesis-card')).toBeNull()
  })

  it('成功：挂出综合结论卡，并回读这次一起跑的评审', async () => {
    const poll = controllablePoll()
    jobSpies.startSynthesisJob.mockResolvedValue(job({ status: 'queued', stage: '' }))
    render(<ReviewPanel target={TARGET} agents={AGENTS} />)
    await waitFor(() => expect(apiSpies.fetchReview).toHaveBeenCalledTimes(1))

    fireEvent.click(await screen.findByRole('button', { name: /生成综合结论/ }))
    await waitFor(() => expect(jobSpies.waitForSynthesisJob).toHaveBeenCalled())
    await act(async () => poll.resolve(job({ status: 'succeeded', stage: '', synthesis })))

    expect((await screen.findByTestId('synthesis-card')).textContent).toContain('综合稿正文')
    // review=true：评审在同一任务里落库，成功后回读一次评审卡
    await waitFor(() => expect(apiSpies.fetchReview).toHaveBeenCalledTimes(2))
  })

  it('失败：给出后端的人话原因，不挂空卡', async () => {
    const poll = controllablePoll()
    jobSpies.startSynthesisJob.mockResolvedValue(job({ status: 'queued', stage: '' }))
    render(<ReviewPanel target={TARGET} agents={AGENTS} />)

    fireEvent.click(await screen.findByRole('button', { name: /生成综合结论/ }))
    await waitFor(() => expect(jobSpies.waitForSynthesisJob).toHaveBeenCalled())
    await act(async () => poll.resolve(job({ status: 'failed', stage: '', error: '综合结论超时未完成，已停止' })))

    expect(toastMock.error).toHaveBeenCalledWith('综合结论失败', { description: '综合结论超时未完成，已停止' })
    expect(screen.queryByTestId('synthesis-card')).toBeNull()
  })

  it('刷新页面：该轮还在跑 → 接着轮询并显示阶段，不重新提交', async () => {
    controllablePoll()
    jobSpies.fetchLatestSynthesisJob.mockResolvedValue(job({ stage: 'review' }))
    render(<ReviewPanel target={TARGET} agents={AGENTS} />)

    await waitFor(() => expect(jobSpies.waitForSynthesisJob).toHaveBeenCalled())
    expect(jobSpies.fetchLatestSynthesisJob).toHaveBeenCalledWith('s-1', 2)
    expect(jobSpies.waitForSynthesisJob.mock.calls[0]?.[1]).toMatchObject({ job_id: 'job-1' })
    await waitFor(() => expect(screen.getByTestId('synthesis-run').textContent).toContain('评审中'))
    expect(jobSpies.startSynthesisJob).not.toHaveBeenCalled()
  })

  it('已结束的历史任务：不轮询、不重复弹失败提示', async () => {
    jobSpies.fetchLatestSynthesisJob.mockResolvedValue(job({ status: 'failed', stage: '', error: '旧失败' }))
    render(<ReviewPanel target={TARGET} agents={AGENTS} />)

    await waitFor(() => expect(jobSpies.fetchLatestSynthesisJob).toHaveBeenCalled())
    expect(jobSpies.waitForSynthesisJob).not.toHaveBeenCalled()
    expect(toastMock.error).not.toHaveBeenCalled()
    expect(screen.getByTestId('synthesis-run').textContent).toContain('生成综合结论')
  })

  it('卸载只停止轮询，不取消后台任务', async () => {
    const poll = controllablePoll()
    jobSpies.fetchLatestSynthesisJob.mockResolvedValue(job())
    const { unmount } = render(<ReviewPanel target={TARGET} agents={AGENTS} />)
    await waitFor(() => expect(jobSpies.waitForSynthesisJob).toHaveBeenCalled())

    unmount()

    expect(poll.signal?.aborted).toBe(true)
    expect(jobSpies.cancelSynthesisJob).not.toHaveBeenCalled()
  })
})

describe('综合的模型下拉跟随执行 agent', () => {
  const LANES = ['pi', 'claude-agent'] as const

  it('换成 claude-agent：下拉只剩它能用的模型，原来选的不能用就自动切到第一个可用的', async () => {
    useCopilot.setState({
      backends: [backend('pi', ['glm53', 'kimi-2.6(Anthropic)']), backend('claude-agent', ['kimi-2.6(Anthropic)'])],
    })
    render(<ReviewPanel target={TARGET} agents={LANES} />)

    const model = (await screen.findByTestId('synthesis-model')) as HTMLSelectElement
    await waitFor(() => expect(model.value).toBe('glm53'))

    fireEvent.change(screen.getByTestId('synthesis-kind'), { target: { value: 'claude-agent' } })

    await waitFor(() => expect(model.value).toBe('kimi-2.6(Anthropic)'))
    const values = Array.from(model.options).map((option) => option.value)
    // 「自动」保留；glm53 不再可选
    expect(values).toEqual(['', 'kimi-2.6(Anthropic)'])
  })

  it('「自动」是律师明确的选择：换 agent 时不被改掉', async () => {
    useCopilot.setState({
      backends: [backend('pi', ['glm53']), backend('claude-agent', ['kimi-2.6(Anthropic)'])],
    })
    render(<ReviewPanel target={TARGET} agents={LANES} />)
    const model = (await screen.findByTestId('synthesis-model')) as HTMLSelectElement
    await waitFor(() => expect(model.value).toBe('glm53'))

    fireEvent.change(model, { target: { value: '' } })
    fireEvent.change(screen.getByTestId('synthesis-kind'), { target: { value: 'claude-agent' } })

    await act(async () => {})
    expect(model.value).toBe('')
  })

  it('所选 agent 一个可用模型都没有：禁用「生成综合结论」并说明原因，不提交任务', async () => {
    useCopilot.setState({ backends: [backend('pi', ['glm53']), backend('claude-agent', [])] })
    render(<ReviewPanel target={TARGET} agents={LANES} />)
    await screen.findByTestId('synthesis-model')

    fireEvent.change(screen.getByTestId('synthesis-kind'), { target: { value: 'claude-agent' } })

    const run = (await screen.findByTestId('synthesis-run')) as HTMLButtonElement
    await waitFor(() => expect(run.disabled).toBe(true))
    expect(screen.getByTestId('synthesis-blocked').textContent).toContain('没有')
    fireEvent.click(run)
    expect(jobSpies.startSynthesisJob).not.toHaveBeenCalled()
  })

  it('后端清单还没拉到：退回平台清单（judge_models），行为与之前一致', async () => {
    render(<ReviewPanel target={TARGET} agents={LANES} />)
    const model = (await screen.findByTestId('synthesis-model')) as HTMLSelectElement
    await waitFor(() => expect(model.value).toBe('judge-a'))
    expect(screen.queryByTestId('synthesis-blocked')).toBeNull()
  })
})
