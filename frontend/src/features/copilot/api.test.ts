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
  delete: vi.fn(),
  patch: vi.fn(),
}))

vi.mock('@/lib/api', () => ({ api: apiMock }))

import {
  createSession,
  decideApproval,
  deleteSession,
  fetchHistory,
  listSessions,
  openMessageStream,
  renameSession,
} from './api'

/** 让 mock 返回链式 .json() */
function chain<T>(value: T) {
  return { json: () => Promise.resolve(value) }
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

  it('createSession: POST 带 title，默认空串', async () => {
    await createSession()
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions', { json: { title: '' } })
  })

  it('createSession: 传入标题', async () => {
    await createSession('新对话')
    expect(apiMock.post).toHaveBeenCalledWith('agent/sessions', { json: { title: '新对话' } })
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
    expect(apiMock.post).toHaveBeenCalledWith('agent/approval/a-1/decide', { json: { approved: true } })
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
})
