/**
 * `loadOlderHistory` / `refreshHistory` 两个翻页动作的状态机（node 环境）。
 *
 * 为什么单独成文件而不是塞进 store.sessions.test.ts：上面那组用例管的是
 * 「切会话」，这组管的是**往上翻历史**，两件事的失败代价完全不同——
 * 切错会话用户一眼能看见，翻页出错则是「滑到顶就一直转圈」或「越翻越多
 * 同一批消息」。
 *
 * 被测的四条契约：
 * - 无 `db-` 消息 / 返回 0 条 / 返回 < 200 条 → 一律置 `noMoreHistory`，
 *   否则用户每次滑到顶都会再打一次必然空的请求；
 * - 返回 200 条 → **不**置，还能继续翻；
 * - `streaming` / `loadingHistory` / `noMoreHistory` / 无会话 四个守卫各自
 *   短路且不发请求（翻页与流式同时进行会把半截回答重复插入转录）；
 * - catch 静默但 `finally` 必须清 `loadingOlder`，否则一次网络抖动就让
 *   「加载更多」按钮永久禁用。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

import * as copilotApi from '../api'
import { useCopilot } from './index'
import type { AgentHistoryMessage } from '../types'

vi.mock('../api', () => ({
  // 登录/接入模型入口（AnswerAgentMenu 的 qoder 行会调）
  startQoderLogin: vi.fn(),
  fetchQoderLoginStatus: vi.fn(),
  registerQoderByok: vi.fn(),
  createSession: vi.fn(),
  fetchHistory: vi.fn(),
  openMessageStream: vi.fn(),
  decideApproval: vi.fn(),
  listSessions: vi.fn(),
  deleteSession: vi.fn(),
  steerSession: vi.fn(),
  clearSessionQueue: vi.fn(),
  submitAgentTask: vi.fn(),
  fetchPendingApprovals: vi.fn(),
  uploadAttachment: vi.fn(),
}))

const fetchHistory = vi.mocked(copilotApi.fetchHistory)

/** 造一行后端历史（message_id 决定 db- 前缀的 id，翻页靠它取 before_id） */
function row(messageId: number): AgentHistoryMessage {
  return { message_id: messageId, role: 'user', content: `消息 ${messageId}` } as AgentHistoryMessage
}

/** 造 n 行历史 */
function rows(n: number, from = 1): AgentHistoryMessage[] {
  return Array.from({ length: n }, (_, i) => row(from + i))
}

/** 转录里已有的消息（最小形状：`loadOlderHistory` 只看 id 前缀） */
function msg(id: string) {
  return { id, role: 'user', content: id } as never
}

beforeEach(() => {
  vi.clearAllMocks()
  // 重置转录与所有翻页标志。**必须显式写死每个字段为 false**：
  // `loadOlderHistory` 有 `loadingHistory / streaming / noMoreHistory` 三个
  // 短路守卫，上一个用例失败路径（比如请求还在飞就断言）若留下 `loadingOlder`
  // 或 `noMoreHistory` 为 true，后面每个用例都会在守卫处静默返回、请求压根
  // 不发，报错却表现为「fetchHistory 没被调用」——排查方向会完全跑偏。
  useCopilot.setState({
    sessionId: null,
    messages: [],
    streaming: false,
    loadingHistory: false,
    loadingOlder: false,
    noMoreHistory: false,
    lastError: null,
    approvals: [],
  })
})

describe('loadOlderHistory：守卫短路', () => {
  it('没有会话时直接返回，不发请求', async () => {
    useCopilot.setState({ sessionId: null, messages: [msg('db-9')] })
    await useCopilot.getState().loadOlderHistory()
    expect(fetchHistory).not.toHaveBeenCalled()
    expect(useCopilot.getState().loadingOlder).toBe(false)
  })

  it('正在加载历史（切会话中）时短路：此时 messages 还是空数组，翻页没有锚点', async () => {
    useCopilot.setState({ sessionId: 's-1', loadingHistory: true, messages: [msg('db-9')] })
    await useCopilot.getState().loadOlderHistory()
    expect(fetchHistory).not.toHaveBeenCalled()
  })

  it('流式中短路：翻页插入会把半截回答与旧消息交错', async () => {
    useCopilot.setState({ sessionId: 's-1', streaming: true, messages: [msg('db-9')] })
    await useCopilot.getState().loadOlderHistory()
    expect(fetchHistory).not.toHaveBeenCalled()
  })

  it('已到顶（noMoreHistory）时短路：否则每次滑到顶都白打一次必然空的请求', async () => {
    useCopilot.setState({ sessionId: 's-1', noMoreHistory: true, messages: [msg('db-9')] })
    await useCopilot.getState().loadOlderHistory()
    expect(fetchHistory).not.toHaveBeenCalled()
  })

  it('转录里没有 db- 消息（全是本地乐观消息）→ 直接判到顶，不发请求', async () => {
    useCopilot.setState({ sessionId: 's-1', messages: [msg('local-1')] })
    await useCopilot.getState().loadOlderHistory()
    // 没有 db- 锚点就没有 before_id，请求无从发起
    expect(fetchHistory).not.toHaveBeenCalled()
    expect(useCopilot.getState().noMoreHistory).toBe(true)
  })
})

describe('loadOlderHistory：翻页结果分档', () => {
  it('用转录里第一条 db- 消息作 before_id，请求 200 条', async () => {
    // 转录是**正序**（旧在上），所以数组里第一个 db- 就是当前最老的一条；
    // 本地乐观消息（local-*）要跳过——它们没有后端 id，拿不来当锚点
    useCopilot.setState({ sessionId: 's-1', messages: [msg('db-5'), msg('db-9'), msg('local-x')] })
    fetchHistory.mockResolvedValue(rows(200))

    await useCopilot.getState().loadOlderHistory()

    expect(fetchHistory).toHaveBeenCalledWith('s-1', 200, 5)
  })

  it('返回 200 条 → 不置 noMoreHistory（还能继续往上翻）', async () => {
    useCopilot.setState({ sessionId: 's-1', messages: [msg('db-200')] })
    fetchHistory.mockResolvedValue(rows(200))

    await useCopilot.getState().loadOlderHistory()

    expect(useCopilot.getState().noMoreHistory).toBe(false)
    expect(useCopilot.getState().messages.length).toBe(201)
  })

  it('返回 < 200 条 → 置 noMoreHistory（后端一次给不满就是到底了）', async () => {
    useCopilot.setState({ sessionId: 's-1', messages: [msg('db-50')] })
    fetchHistory.mockResolvedValue(rows(3))

    await useCopilot.getState().loadOlderHistory()

    expect(useCopilot.getState().noMoreHistory).toBe(true)
    expect(useCopilot.getState().messages.length).toBe(4)
  })

  it('返回 0 条 → 置 noMoreHistory 且不动转录', async () => {
    useCopilot.setState({ sessionId: 's-1', messages: [msg('db-50')] })
    fetchHistory.mockResolvedValue([])

    await useCopilot.getState().loadOlderHistory()

    expect(useCopilot.getState().noMoreHistory).toBe(true)
    expect(useCopilot.getState().messages.map((m) => m.id)).toEqual(['db-50'])
  })

  it('旧消息插在最前面（翻页方向是向上，插末尾会当场错位）', async () => {
    useCopilot.setState({ sessionId: 's-1', messages: [msg('db-30')] })
    fetchHistory.mockResolvedValue(rows(2, 10))

    await useCopilot.getState().loadOlderHistory()

    expect(useCopilot.getState().messages.map((m) => m.id)).toEqual(['db-10', 'db-11', 'db-30'])
  })

  it('成功路径的 finally 也清 loadingOlder', async () => {
    useCopilot.setState({ sessionId: 's-1', messages: [msg('db-30')] })
    fetchHistory.mockResolvedValue(rows(2, 10))

    await useCopilot.getState().loadOlderHistory()

    expect(useCopilot.getState().loadingOlder).toBe(false)
  })
})

describe('loadOlderHistory：失败处理', () => {
  it('请求失败静默（不设 lastError、不打扰当前对话），但必须清 loadingOlder', async () => {
    useCopilot.setState({ sessionId: 's-1', messages: [msg('db-30')] })
    fetchHistory.mockRejectedValue(new Error('网络抖动'))

    await useCopilot.getState().loadOlderHistory()

    // 不清 loadingOlder 的话「加载更多」按钮会永久禁用，只能刷新页面
    expect(useCopilot.getState().loadingOlder).toBe(false)
    // 翻页失败不该改 noMoreHistory：用户重试仍有可能拿到数据
    expect(useCopilot.getState().noMoreHistory).toBe(false)
    expect(useCopilot.getState().lastError).toBeNull()
  })
})

describe('refreshHistory', () => {
  it('无会话 / 流式中都短路，不发请求', async () => {
    useCopilot.setState({ sessionId: null })
    await useCopilot.getState().refreshHistory()
    useCopilot.setState({ sessionId: 's-1', streaming: true })
    await useCopilot.getState().refreshHistory()
    expect(fetchHistory).not.toHaveBeenCalled()
  })

  it('重新拉整段历史并整体替换转录', async () => {
    useCopilot.setState({ sessionId: 's-1', messages: [msg('local-old')] })
    fetchHistory.mockResolvedValue(rows(2, 7))

    await useCopilot.getState().refreshHistory()

    expect(fetchHistory).toHaveBeenCalledWith('s-1')
    expect(useCopilot.getState().messages.map((m) => m.id)).toEqual(['db-7', 'db-8'])
  })

  it('等待期间会话被切走：迟到的结果不得覆盖新会话的转录', async () => {
    useCopilot.setState({ sessionId: 's-1', messages: [] })
    let resolve!: (v: AgentHistoryMessage[]) => void
    fetchHistory.mockReturnValue(
      new Promise<AgentHistoryMessage[]>((r) => {
        resolve = r
      }),
    )

    const pending = useCopilot.getState().refreshHistory()
    // 律师在请求在飞时切到了另一个会话
    useCopilot.setState({ sessionId: 's-2', messages: [msg('db-100')] })
    resolve(rows(2, 1))
    await pending

    // 覆盖的话 s-2 里会突然出现 s-1 的消息（串台，最严重的一类脏数据）
    expect(useCopilot.getState().messages.map((m) => m.id)).toEqual(['db-100'])
  })

  it('失败静默：轮询刷新失败不该影响现有转录', async () => {
    useCopilot.setState({ sessionId: 's-1', messages: [msg('db-1')] })
    fetchHistory.mockRejectedValue(new Error('boom'))

    await useCopilot.getState().refreshHistory()

    expect(useCopilot.getState().messages.map((m) => m.id)).toEqual(['db-1'])
    expect(useCopilot.getState().lastError).toBeNull()
  })
})
