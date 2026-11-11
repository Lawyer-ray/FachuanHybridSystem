/**
 * settings api 单测（node 环境）。
 *
 * 系统状态卡的数据来源，容易被当成「随便拼路径」——这里把四个端点的
 * 路径与参数形状钉住（尤其 /llm/models 的 `{models}` 信封要拆开、
 * probeBackend 的耗时是四舍五入的整数 ms）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))

vi.mock('@/lib/api', () => ({ api: { get, post } }))

import { fetchAgentUsage, fetchLlmModels, fetchQClusterStatus, probeBackend, testLlmConnection } from './api'

const reply = <T,>(value: T) => ({ json: () => Promise.resolve(value) })

beforeEach(() => {
  vi.clearAllMocks()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('fetchQClusterStatus', () => {
  it('GET task-queue/cluster-status 原样返回（clusters=null 表示探测不到，不转成 0）', async () => {
    const status = {
      clusters: null,
      queue_depth: 3,
      succeeded_today: 12,
      failed_today: 1,
      last_success_at: null,
      last_failed_at: null,
      broker_error: '连接被拒绝',
    }
    get.mockReturnValue(reply(status))
    await expect(fetchQClusterStatus()).resolves.toEqual(status)
    expect(get).toHaveBeenCalledWith('task-queue/cluster-status')
  })
})

describe('fetchLlmModels', () => {
  it('拆开 {models} 信封，只返回数组', async () => {
    const models = [{ id: 'gpt-4.1', name: 'GPT-4.1', backend: 'openai', context_window: 128000 }]
    get.mockReturnValue(reply({ models }))
    await expect(fetchLlmModels()).resolves.toEqual(models)
    expect(get).toHaveBeenCalledWith('llm/models')
  })
})

describe('fetchAgentUsage', () => {
  it('默认查 1 天，days 以字符串传（searchParams 只收 string|number）', async () => {
    const usage = {
      runs: 10,
      ok_runs: 9,
      error_runs: 1,
      cancelled_runs: 0,
      error_rate: 0.1,
      avg_duration_ms: 1200,
    }
    get.mockReturnValue(reply(usage))
    await expect(fetchAgentUsage()).resolves.toEqual(usage)
    expect(get).toHaveBeenCalledWith('agent/usage', { searchParams: { days: '1' } })
  })

  it('自定义天数透传', async () => {
    get.mockReturnValue(reply({}))
    await fetchAgentUsage(7)
    expect(get).toHaveBeenCalledWith('agent/usage', { searchParams: { days: '7' } })
  })
})

describe('testLlmConnection', () => {
  it('POST llm/test-connection?model_id=…，无请求体', async () => {
    post.mockReturnValue(reply({ ok: true, model: 'gpt-4.1', backend: 'openai' }))
    await expect(testLlmConnection('gpt-4.1')).resolves.toEqual({ ok: true, model: 'gpt-4.1', backend: 'openai' })
    expect(post).toHaveBeenCalledWith('llm/test-connection', { searchParams: { model_id: 'gpt-4.1' } })
  })
})

describe('probeBackend', () => {
  it('返回一次鉴权 GET 的往返毫秒数（四舍五入为整数）', async () => {
    let t = 0
    vi.stubGlobal('performance', {
      now: () => {
        t += 12.4
        return t
      },
    })
    get.mockReturnValue(reply({ id: 1 }))

    await expect(probeBackend()).resolves.toBe(12)
    expect(get).toHaveBeenCalledWith('organization/me')
  })

  it('请求失败即视为不可达：错误向上抛，不吞成「0ms」', async () => {
    vi.stubGlobal('performance', { now: () => 0 })
    get.mockReturnValue({ json: () => Promise.reject(new Error('网络错误')) })
    await expect(probeBackend()).rejects.toThrow('网络错误')
  })
})
