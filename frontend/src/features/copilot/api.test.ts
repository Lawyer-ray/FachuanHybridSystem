/**
 * copilot API 客户端的路径与参数契约测试（node 环境）。
 *
 * 这些端点路径与后端 agent_api 一一对应，路径写错只会在运行时才暴露，
 * 故用 mock ky 实例断言实际发出的 method / url / 参数。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  put: vi.fn(),
  delete: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ api: apiMock, UPLOAD_TIMEOUT_MS: 300_000 }))

import {
  clearScopeFolderRowsCache,
  createSession,
  fetchCaseFolderEntries,
  fetchContractFolderEntries,
  globalSearch,
  loadScopeFolderRows,
  fetchBackends,
  uploadAttachment,
  decideApproval,
  deleteSession,
  fetchHistory,
  fetchPendingApprovals,
  fetchReviewOptions,
  fetchSynthesis,
  getUsageSummary,
  listSessions,
  openMessageStream,
  renameSession,
  steerSession,
  submitAgentTask,
  fetchAgentSkills,
  fetchAgentSkill,
  createAgentSkill,
  updateAgentSkill,
  deleteAgentSkill,
  validateAgentSkill,
  duplicateAgentSkill,
  setAgentSkillEnabled,
  fetchSessionStats,
  compactSession,
  REVIEW_TIMEOUT_MS,
  runReview,
  runSynthesis,
} from './api'
import {
  cancelSynthesisJob,
  fetchLatestSynthesisJob,
  fetchSynthesisJob,
  startSynthesisJob,
  SYNTHESIS_SUBMIT_TIMEOUT_MS,
  SynthesisWaitTimeoutError,
  waitForSynthesisJob,
} from './review-api'
import type { SynthesisJob } from './adjudication-types'

/** 让 mock 返回链式 .json() */
function chain<T>(value: T) {
  return { json: () => Promise.resolve(value) }
}

/** 综合任务的 wire 形状（轮询用例按需覆盖 status / stage） */
function jobWire(over: Partial<SynthesisJob> = {}): SynthesisJob {
  return {
    job_id: 'job-1',
    session_id: 's-1',
    turn: 2,
    status: 'queued',
    stage: '',
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

beforeEach(() => {
  vi.clearAllMocks()
  for (const k of Object.keys(apiMock) as Array<keyof typeof apiMock>) {
    apiMock[k].mockReturnValue(chain({}))
  }
})

describe('copilot api', () => {
  it('listSessions: GET agent/sessions，默认 limit=50', async () => {
    apiMock.get.mockReturnValue(chain([]))
    await listSessions()
    expect(apiMock.get).toHaveBeenCalledWith('agent/sessions', { searchParams: { limit: 50 } })
  })

  it('listSessions: 可覆盖 limit', async () => {
    apiMock.get.mockReturnValue(chain([]))
    await listSessions(10)
    expect(apiMock.get).toHaveBeenCalledWith('agent/sessions', { searchParams: { limit: 10 } })
  })

  it('listSessions: 业务范围过滤带 origin + case_id/contract_id（P1-1）', async () => {
    apiMock.get.mockReturnValue(chain([]))
    await listSessions(50, { origin: 'case', refId: 9 })
    expect(apiMock.get).toHaveBeenCalledWith('agent/sessions', {
      searchParams: { limit: 50, origin: 'case', case_id: 9 },
    })
    await listSessions(50, { origin: 'contract', refId: 386 })
    expect(apiMock.get).toHaveBeenLastCalledWith('agent/sessions', {
      searchParams: { limit: 50, origin: 'contract', contract_id: 386 },
    })
  })

  it('createSession: POST 带 title，默认空串', async () => {
    await createSession()
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions', { json: { title: '' } })
  })

  it('createSession: 传入标题', async () => {
    await createSession('新对话')
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions', { json: { title: '新对话' } })
  })

  it('createSession: 业务范围内建会话带 origin + contract_id/case_id（P1-1）', async () => {
    await createSession('', { origin: 'contract', refId: 386 })
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions', {
      json: { title: '', origin: 'contract', contract_id: 386 },
    })
    await createSession('', { origin: 'case', refId: 12 })
    expect(apiMock.post).toHaveBeenLastCalledWith('agent/sessions', {
      json: { title: '', origin: 'case', case_id: 12 },
    })
  })

  it('createSession: 指定 agent_kind 时带进请求体（会话级后端选择）', async () => {
    await createSession('', undefined, 'dsh')
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions', { json: { title: '', agent_kind: 'dsh' } })
  })

  it('createSession: 未指定 agent_kind 时不发该字段（交给服务端默认 pi）', async () => {
    await createSession('新对话')
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions', { json: { title: '新对话' } })
  })

  it('createSession: agent_kind 与业务范围可同时带', async () => {
    await createSession('', { origin: 'case', refId: 12 }, 'dsh')
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions', {
      json: { title: '', origin: 'case', case_id: 12, agent_kind: 'dsh' },
    })
  })

  it('fetchBackends: GET agent/backends（切换器数据源）', async () => {
    apiMock.get.mockReturnValue(chain([]))
    await fetchBackends()
    expect(apiMock.get).toHaveBeenCalledWith('agent/backends')
  })

  it('deleteSession: DELETE 带会话 id', async () => {
    await deleteSession('s-1')
    expect(apiMock.delete).toHaveBeenCalledWith('agent/sessions/s-1')
  })

  it('renameSession: PATCH 带 title', async () => {
    await renameSession('s-1', '改名')
    expect(apiMock.patch).toHaveBeenCalledWith('agent/sessions/s-1', { json: { title: '改名' } })
  })

  it('fetchHistory: GET messages，默认 limit=200', async () => {
    apiMock.get.mockReturnValue(chain([]))
    await fetchHistory('s-1')
    expect(apiMock.get).toHaveBeenCalledWith('agent/sessions/s-1/messages', { searchParams: { limit: 200 } })
  })

  it('decideApproval: POST 带 approved 布尔', async () => {
    await decideApproval('a-1', true)
    expect(apiMock.post).toHaveBeenCalledWith('agent/approval/a-1/decide', { json: { approved: true, reason: '' } })
  })

  it('openMessageStream: POST 带 message 与 signal，且返回未消费的 Response', async () => {
    const signal = new AbortController().signal
    const resp = new Response('data: x', { status: 200 })
    apiMock.post.mockReturnValue(Promise.resolve(resp))

    const got = await openMessageStream('s-1', '你好', signal)
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions/s-1/messages', {
      json: { message: '你好' },
      signal,
    })
    // body 必须仍可读（store 自己读流）
    expect(got.body).not.toBeNull()
  })

  it('openMessageStream: agents 原样下发（顺序 = 栏序，多答靠它表达）', async () => {
    apiMock.post.mockReturnValue(Promise.resolve(new Response('data: x')))
    await openMessageStream('s-1', '你好', new AbortController().signal, [{ kind: 'dsh' }, { kind: 'pi' }, { kind: 'oai' }])
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions/s-1/messages', {
      json: { message: '你好', agents: [{ kind: 'dsh' }, { kind: 'pi' }, { kind: 'oai' }] },
      signal: expect.anything(),
    })
  })

  it('openMessageStream: 每栏可带模型（{kind, model} 对象形状，与后端 AgentSpecIn 同形）', async () => {
    apiMock.post.mockReturnValue(Promise.resolve(new Response('data: x')))
    await openMessageStream('s-1', '你好', new AbortController().signal, [
      { kind: 'pi', model: 'kimi-2.6' },
      { kind: 'dsh' },
    ])
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions/s-1/messages', {
      json: { message: '你好', agents: [{ kind: 'pi', model: 'kimi-2.6' }, { kind: 'dsh' }] },
      signal: expect.anything(),
    })
  })

  it('openMessageStream: 单个 agent 也下发（单跑指定后端）', async () => {
    apiMock.post.mockReturnValue(Promise.resolve(new Response('data: x')))
    await openMessageStream('s-1', '你好', new AbortController().signal, [{ kind: 'dsh' }])
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions/s-1/messages', {
      json: { message: '你好', agents: [{ kind: 'dsh' }] },
      signal: expect.anything(),
    })
  })

  it('openMessageStream: 空 agents 不发字段（不传 = 后端单跑会话默认后端）', async () => {
    apiMock.post.mockReturnValue(Promise.resolve(new Response('data: x')))
    await openMessageStream('s-1', '你好', new AbortController().signal, [])
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions/s-1/messages', {
      json: { message: '你好' },
      signal: expect.anything(),
    })
  })

  it('steerSession: POST steer 带 message（P0-2）', async () => {
    await steerSession('s-1', '补充')
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions/s-1/steer', { json: { message: '补充' } })
  })

  it('submitAgentTask: POST tasks；业务范围带归属（P1-1）', async () => {
    await submitAgentTask('梳理材料')
    expect(apiMock.post).toHaveBeenCalledWith('agent/tasks', { json: { message: '梳理材料', title: '' } })
    await submitAgentTask('梳理材料', '标题', { origin: 'case', refId: 9 })
    expect(apiMock.post).toHaveBeenLastCalledWith('agent/tasks', {
      json: { message: '梳理材料', title: '标题', origin: 'case', case_id: 9 },
    })
  })

  it('fetchPendingApprovals: GET 待审列表（P0-3）', async () => {
    apiMock.get.mockReturnValue(chain([]))
    await fetchPendingApprovals()
    expect(apiMock.get).toHaveBeenCalledWith('agent/approvals/pending')
  })

  it('getUsageSummary: GET usage 带 days；all=true 透传（P1-2）', async () => {
    apiMock.get.mockReturnValue(chain({}))
    await getUsageSummary(30)
    expect(apiMock.get).toHaveBeenCalledWith('agent/usage', { searchParams: { days: 30 } })
    await getUsageSummary(7, true)
    expect(apiMock.get).toHaveBeenLastCalledWith('agent/usage', { searchParams: { days: 7, all: 'true' } })
  })
})

describe('copilot api：附件（P1-11）', () => {
  it('uploadAttachment: POST multipart（FormData 不设 json）', async () => {
    apiMock.post.mockReturnValue(chain({}))
    const file = new File(['x'], 'a.txt', { type: 'text/plain' })
    await uploadAttachment('s-1', file)
    const call = apiMock.post.mock.calls[0]!
    expect(call[0]).toBe('agent/sessions/s-1/attachments')
    const body = call[1].body as FormData
    expect(body).toBeInstanceOf(FormData)
    expect(body.get('file')).toBe(file)
    // 大文件上传走 300s 口径，不吃默认 10s
    expect(call[1].timeout).toBe(300_000)
  })
})

// ── 技能 / 统计 / 压缩（`/` 菜单与上下文水位的数据源）────────────────────────

describe('skills & stats & compact api', () => {
  it('fetchAgentSkills GET agent/skills', async () => {
    apiMock.get.mockReturnValueOnce(chain({ skills: [] }))
    await fetchAgentSkills()
    expect(apiMock.get).toHaveBeenCalledWith('agent/skills')
  })

  it('setAgentSkillEnabled PATCH agent/skills/{key} 带 enabled', async () => {
    apiMock.patch.mockReturnValueOnce(chain({ key: 'builtin:web-research', enabled: false }))
    await setAgentSkillEnabled('builtin:web-research', false)
    expect(apiMock.patch).toHaveBeenCalledWith('agent/skills/builtin%3Aweb-research', { json: { enabled: false } })
  })

  /**
   * key 的 URL 编码：内置 key 是 `builtin:<name>`、个人是 `skill:<uuid>`，`:`
   * 原样拼进路径会被 URL 解析吃掉（或当成其它语义）——每个按 key 的端点都得过一遍。
   */
  it('所有按 key 的端点都把 `:` 编码成 %3A', async () => {
    const encoded = 'agent/skills/builtin%3Aweb-research'
    apiMock.get.mockReturnValueOnce(chain({ key: 'builtin:web-research', body: '' }))
    await fetchAgentSkill('builtin:web-research')
    expect(apiMock.get).toHaveBeenLastCalledWith(encoded)

    apiMock.put.mockReturnValueOnce(chain({ key: 'builtin:web-research' }))
    await updateAgentSkill('builtin:web-research', { title: 't', description: 'd', body: 'b', version: 1 })
    expect(apiMock.put).toHaveBeenLastCalledWith(encoded, {
      json: { title: 't', description: 'd', body: 'b', version: 1 },
    })

    apiMock.delete.mockReturnValueOnce(Promise.resolve({}))
    await deleteAgentSkill('builtin:web-research')
    expect(apiMock.delete).toHaveBeenLastCalledWith(encoded)

    apiMock.post.mockReturnValueOnce(chain({ key: 'builtin:web-research' }))
    await duplicateAgentSkill('builtin:web-research')
    expect(apiMock.post).toHaveBeenLastCalledWith(`${encoded}/duplicate`)
  })

  it('createAgentSkill POST agent/skills；validateAgentSkill POST agent/skills/validate', async () => {
    const input = { name: 'skill-ab12', title: '合同审查三段式', description: '审合同', body: '1. 主体' }
    apiMock.post.mockReturnValueOnce(chain({ key: 'skill:1' }))
    await createAgentSkill(input)
    expect(apiMock.post).toHaveBeenLastCalledWith('agent/skills', { json: input })

    apiMock.post.mockReturnValueOnce(chain({ ok: true, errors: [], preview: '---' }))
    await validateAgentSkill(input)
    expect(apiMock.post).toHaveBeenLastCalledWith('agent/skills/validate', { json: input })
  })

  it('fetchSessionStats GET agent/sessions/{id}/stats', async () => {
    apiMock.get.mockReturnValueOnce(chain({ output_tokens: 0 }))
    await fetchSessionStats('s-1')
    expect(apiMock.get).toHaveBeenCalledWith('agent/sessions/s-1/stats')
  })

  it('compactSession POST agent/sessions/{id}/compact', async () => {
    apiMock.post.mockReturnValueOnce(chain({ compacted: true }))
    await compactSession('s-1')
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions/s-1/compact')
  })
})

/**
 * `@` 引用候选源的端点契约。
 *
 * 这几个路径不是猜的：`GET /search`（core/api/search_api.py，前缀见 api.py:320）、
 * `GET /cases/{id}/folder-entries`（case_folder_browse_api.py:54，前缀 api.py:215）、
 * `GET /contracts/{id}/folder-entries`（folder_binding_api.py，前缀 api.py:217）。
 * 路径写错的症状是「@ 永远没候选、控制台也不报」——所以在这里钉死。
 */
describe('copilot api：@ 引用候选源', () => {
  it('globalSearch GET search 带 q/limit（空 q 与 limit 上限由后端管）', async () => {
    apiMock.get.mockReturnValue(chain({ cases: [], contracts: [] }))
    await globalSearch('张三', 8)
    expect(apiMock.get).toHaveBeenCalledWith('search', { searchParams: { q: '张三', limit: 8 } })
  })

  it('globalSearch 带 AbortSignal（查询词变了要能中断上一轮）', async () => {
    apiMock.get.mockReturnValue(chain({ cases: [], contracts: [] }))
    const controller = new AbortController()
    await globalSearch('张三', 8, controller.signal)
    expect(apiMock.get).toHaveBeenCalledWith('search', {
      searchParams: { q: '张三', limit: 8 },
      signal: controller.signal,
    })
  })

  it('fetchCaseFolderEntries GET cases/{id}/folder-entries（subpath 为空时不带参数）', async () => {
    apiMock.get.mockReturnValue(chain({ browsable: true, folders: [], files: [] }))
    await fetchCaseFolderEntries(7)
    expect(apiMock.get).toHaveBeenCalledWith('cases/7/folder-entries', { searchParams: {} })
    await fetchCaseFolderEntries(7, '1-一审')
    expect(apiMock.get).toHaveBeenLastCalledWith('cases/7/folder-entries', { searchParams: { subpath: '1-一审' } })
  })

  it('fetchContractFolderEntries GET contracts/{id}/folder-entries', async () => {
    apiMock.get.mockReturnValue(chain({ browsable: true, folders: [], files: [] }))
    await fetchContractFolderEntries(5, '2-立案材料')
    expect(apiMock.get).toHaveBeenCalledWith('contracts/5/folder-entries', { searchParams: { subpath: '2-立案材料' } })
  })

  it('loadScopeFolderRows：根层 + 前 6 个子目录合并，结果按范围缓存', async () => {
    clearScopeFolderRowsCache()
    apiMock.get.mockImplementation((_url: string, options: { searchParams?: { subpath?: string } } = {}) => {
      const subpath = options.searchParams?.subpath
      // 根层：8 个子目录 + 1 个文件（只应扫前 6 个子目录）
      if (!subpath) {
        return chain({
          browsable: true,
          folders: Array.from({ length: 8 }, (_, i) => ({ name: `目录${i}`, subpath: `d${i}` })),
          files: [{ name: '根文件.pdf', subpath: '根文件.pdf', size: 2048, modified_at: '' }],
        })
      }
      return chain({
        browsable: true,
        folders: [],
        files: [{ name: '起诉状.pdf', subpath: `${subpath}/起诉状.pdf`, size: 1024, modified_at: '' }],
      })
    })

    const rows = await loadScopeFolderRows({ origin: 'case', refId: 7 })
    // 根 1 + 前 6 个子目录（第 7/8 个不扫：一次菜单只允许一轮有界的请求）
    expect(apiMock.get).toHaveBeenCalledTimes(7)
    expect(rows.files.map((f) => f.name)).toEqual(['根文件.pdf', ...Array.from({ length: 6 }, () => '起诉状.pdf')])

    // 第二个查询词命中缓存，不再发请求
    const again = await loadScopeFolderRows({ origin: 'case', refId: 7 })
    expect(again.files).toHaveLength(7)
    expect(apiMock.get).toHaveBeenCalledTimes(7)
    clearScopeFolderRowsCache()
  })

  it('fetchReviewOptions GET agent/review/options（judge_models 空 = 平台无可用模型）', async () => {
    apiMock.get.mockReturnValue(chain({ rubric_ids: ['contract_answer_v1'], judge_models: [], max_lanes: 4 }))
    await expect(fetchReviewOptions()).resolves.toEqual({
      rubric_ids: ['contract_answer_v1'],
      judge_models: [],
      max_lanes: 4,
    })
    expect(apiMock.get).toHaveBeenCalledWith('agent/review/options')
  })

  it('runReview POST sessions/{id}/review：请求体 snake_case，超时用评审专用预算', async () => {
    await runReview('s-1', { turn: 2, agents: ['pi', 'dsh'], rubricId: 'contract_answer_v1', judgeModels: ['judge-a'] })
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions/s-1/review', {
      json: {
        turn: 2,
        agents: ['pi', 'dsh'],
        rubric_id: 'contract_answer_v1',
        judge_models: ['judge-a'],
      },
      // ky 默认 10s；评审是 N×M 次 judge 调用，必超时
      timeout: REVIEW_TIMEOUT_MS,
    })
  })

  it('fetchSynthesis GET sessions/{id}/synthesis?turn=（404 = 该轮没跑过，正常态）', async () => {
    await fetchSynthesis('s-1', 3)
    expect(apiMock.get).toHaveBeenCalledWith('agent/sessions/s-1/synthesis', { searchParams: { turn: 3 } })
  })

  it('startSynthesisJob POST sessions/{id}/synthesize：立即返回任务；model 空串照发 + agent/评审/凭证口径', async () => {
    await startSynthesisJob('s-1', { turn: 3, agents: ['pi', 'dsh'], model: '' })
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions/s-1/synthesize', {
      json: {
        turn: 3,
        agents: ['pi', 'dsh'],
        model: '',
        // 默认 pi（与后端 agent_runner.DEFAULT_SYNTHESIS_KIND 同值）
        kind: 'pi',
        // 默认先评审：评审分数是综合取舍的依据
        review: true,
        // 省略 = 服务端自动挑本所的威科账号
        credential_id: null,
      },
      // 提交只做校验与入队：不再需要评审那样的长超时
      timeout: SYNTHESIS_SUBMIT_TIMEOUT_MS,
    })
  })

  it('startSynthesisJob 透传选中的 agent / 模型 / 先评审开关 / 凭证', async () => {
    await startSynthesisJob('s-1', {
      turn: 2,
      agents: ['pi'],
      model: 'glm53',
      kind: 'claude-agent',
      review: false,
      credentialId: 7,
    })
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions/s-1/synthesize', {
      json: { turn: 2, agents: ['pi'], model: 'glm53', kind: 'claude-agent', review: false, credential_id: 7 },
      timeout: SYNTHESIS_SUBMIT_TIMEOUT_MS,
    })
  })

  it('综合任务的查询 / 最近一次 / 取消路径', async () => {
    await fetchSynthesisJob('s-1', 'job-1')
    expect(apiMock.get).toHaveBeenCalledWith('agent/sessions/s-1/synthesis/jobs/job-1')
    await fetchLatestSynthesisJob('s-1', 3)
    expect(apiMock.get).toHaveBeenCalledWith('agent/sessions/s-1/synthesis/jobs', { searchParams: { turn: 3 } })
    await cancelSynthesisJob('s-1', 'job-1')
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions/s-1/synthesis/jobs/job-1/cancel')
  })

  it('waitForSynthesisJob 轮询到终态，每次进展回调 onUpdate', async () => {
    apiMock.get
      .mockReturnValueOnce(chain(jobWire({ status: 'running', stage: 'review' })))
      .mockReturnValueOnce(chain(jobWire({ status: 'running', stage: 'verify' })))
      .mockReturnValueOnce(chain(jobWire({ status: 'succeeded', stage: '' })))
    const updates: string[] = []
    const finished = await waitForSynthesisJob('s-1', jobWire({ status: 'queued' }), {
      intervalMs: 1,
      onUpdate: (job) => updates.push(`${job.status}:${job.stage}`),
    })
    expect(finished.status).toBe('succeeded')
    expect(updates).toEqual(['running:review', 'running:verify', 'succeeded:'])
    expect(apiMock.get).toHaveBeenCalledTimes(3)
  })

  it('waitForSynthesisJob 中止 = 只停轮询（AbortError），不再请求、更不调取消接口', async () => {
    apiMock.get.mockReturnValue(chain(jobWire({ status: 'running' })))
    const controller = new AbortController()
    const pending = waitForSynthesisJob('s-1', jobWire({ status: 'running' }), {
      intervalMs: 50,
      signal: controller.signal,
    })
    controller.abort()
    await expect(pending).rejects.toMatchObject({ name: 'AbortError' })
    expect(apiMock.get).not.toHaveBeenCalled()
    expect(apiMock.post).not.toHaveBeenCalled()
  })

  it('waitForSynthesisJob 超过总上限：给出可读提示（后台任务不受影响）', async () => {
    apiMock.get.mockReturnValue(chain(jobWire({ status: 'running' })))
    await expect(
      waitForSynthesisJob('s-1', jobWire({ status: 'running' }), { intervalMs: 1, maxWaitMs: 5 }),
    ).rejects.toBeInstanceOf(SynthesisWaitTimeoutError)
  })

  it('waitForSynthesisJob 偶发失败会重试，连续 3 次失败才放弃', async () => {
    const boom = { json: () => Promise.reject(new Error('网络抖动')) }
    apiMock.get
      .mockReturnValueOnce(boom)
      .mockReturnValueOnce(boom)
      .mockReturnValueOnce(chain(jobWire({ status: 'succeeded' })))
    await expect(waitForSynthesisJob('s-1', jobWire({ status: 'running' }), { intervalMs: 1 })).resolves.toMatchObject({
      status: 'succeeded',
    })

    apiMock.get.mockReset()
    apiMock.get.mockReturnValue(boom)
    await expect(waitForSynthesisJob('s-1', jobWire({ status: 'running' }), { intervalMs: 1 })).rejects.toThrow('网络抖动')
    expect(apiMock.get).toHaveBeenCalledTimes(3)
  })

  it('runSynthesis = 提交 + 轮询：成功返回结论，失败带后端原因', async () => {
    const synthesis = { synthesis_id: 'syn-1', text: '结论' }
    apiMock.post.mockReturnValueOnce(chain(jobWire({ status: 'queued' })))
    apiMock.get.mockReturnValueOnce(chain(jobWire({ status: 'succeeded', synthesis: synthesis as never })))
    await expect(runSynthesis('s-1', { turn: 2, agents: ['pi'], model: '' }, { intervalMs: 1 })).resolves.toEqual(
      synthesis,
    )

    apiMock.post.mockReturnValueOnce(chain(jobWire({ status: 'failed', error: '没有可用模型' })))
    await expect(runSynthesis('s-1', { turn: 2, agents: ['pi'], model: '' })).rejects.toThrow('没有可用模型')
  })

  it('loadScopeFolderRows：未绑定文件夹 → browsable=false，不报错', async () => {
    clearScopeFolderRowsCache()
    apiMock.get.mockReturnValue(chain({ browsable: false, message: '该案件未绑定文件夹', folders: [], files: [] }))
    await expect(loadScopeFolderRows({ origin: 'case', refId: 9 })).resolves.toEqual({
      browsable: false,
      message: '该案件未绑定文件夹',
      folders: [],
      files: [],
    })
    clearScopeFolderRowsCache()
  })
})
