/**
 * store：agent 后端选择（切换器状态流转）。
 *
 * 三组验收点——它们对应三条会「静默出错」的路径：
 * 1. `send` 建会话时下发 `agent_kind`：勾了 agent 时是**本轮勾选的第一个**（过滤掉
 *    不可用的），一个都不勾才是 `selectedAgentKind`。发错不会报错，用户以为换了
 *    后端却在用 pi 跑（`agent_kind` 建完不可改，整段会话都错）；
 * 2. 不可用的后端选不中。选中灰项 → 建会话才 400，那时用户已经丢掉了一次操作；
 * 3. 偏好跨刷新 / 登出收敛：持久化的 kind 已下线时回落默认，而不是让界面停在
 *    一个选不中的值上。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

// 默认测试环境是 node（无 localStorage）：本文件的持久化断言需要一个最小实现。
// 模块级定义而不是逐用例 mock——store 首次导入就会 `readStoredAgentKind()`。
class MemoryStorage {
  private data = new Map<string, string>()
  getItem(key: string): string | null {
    return this.data.get(key) ?? null
  }
  setItem(key: string, value: string): void {
    this.data.set(key, value)
  }
  removeItem(key: string): void {
    this.data.delete(key)
  }
  clear(): void {
    this.data.clear()
  }
}
vi.stubGlobal('localStorage', new MemoryStorage())

import * as copilotApi from './api'
import { DEFAULT_CAPABILITIES, defaultAgentKind, findBackend, resolveCapabilities } from './store/backends'
import { useCopilot } from './store'
import type { AgentBackendOption, AgentSession } from './types'

vi.mock('./api', () => ({
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
  fetchBackends: vi.fn(),
  fetchSessionStats: vi.fn(),
}))

const encoder = new TextEncoder()

function sseResponse(frames: string[]): Response {
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const frame of frames) controller.enqueue(encoder.encode(frame))
      controller.close()
    },
  })
  return new Response(body, { status: 200 })
}

const session: AgentSession = {
  session_id: 's-1',
  title: '',
  status: 'active',
  llm_model: '',
  agent_kind: 'pi',
  created_at: '',
  updated_at: '',
}

function option(kind: string, available = true, reason = ''): AgentBackendOption {
  return {
    kind,
    label: kind === 'pi' ? 'Pi' : 'DeepSeek Harness',
    description: '',
    available,
    reason,
    capabilities: { streaming: true, tool_calls: true, approval: true, compaction: true, steer: kind === 'pi', concurrent_in_session: false },
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  localStorage.clear()
  useCopilot.getState().reset()
  useCopilot.setState({ backends: [], selectedAgentKind: '' })
})

describe('copilot store：后端清单加载', () => {
  it('拉到清单后默认选第一项可用后端，并落盘', async () => {
    vi.mocked(copilotApi.fetchBackends).mockResolvedValue([option('pi'), option('dsh')])

    await useCopilot.getState().loadBackends()

    const s = useCopilot.getState()
    expect(s.backends.map((b) => b.kind)).toEqual(['pi', 'dsh'])
    expect(s.selectedAgentKind).toBe('pi')
    expect(localStorage.getItem('copilot:agent-kind')).toBe('pi')
  })

  it('保留仍可用的既有偏好（不把用户的选择冲成默认）', async () => {
    useCopilot.setState({ selectedAgentKind: 'dsh' })
    vi.mocked(copilotApi.fetchBackends).mockResolvedValue([option('pi'), option('dsh')])

    await useCopilot.getState().loadBackends()

    expect(useCopilot.getState().selectedAgentKind).toBe('dsh')
  })

  it('偏好已不可用时回落第一项可用后端', async () => {
    useCopilot.setState({ selectedAgentKind: 'dsh' })
    vi.mocked(copilotApi.fetchBackends).mockResolvedValue([option('pi'), option('dsh', false, '未安装 DeepSeek Harness SDK')])

    await useCopilot.getState().loadBackends()

    expect(useCopilot.getState().selectedAgentKind).toBe('pi')
    expect(localStorage.getItem('copilot:agent-kind')).toBe('pi')
  })

  it('偏好已下线（清单里没这个 kind）时同样回落', async () => {
    useCopilot.setState({ selectedAgentKind: 'gone' })
    vi.mocked(copilotApi.fetchBackends).mockResolvedValue([option('pi')])

    await useCopilot.getState().loadBackends()

    expect(useCopilot.getState().selectedAgentKind).toBe('pi')
  })

  it('全部不可用时回落空串（= 不指定，交给后端默认），不硬选灰项', async () => {
    vi.mocked(copilotApi.fetchBackends).mockResolvedValue([option('pi', false, '未找到 pi 可执行文件')])

    await useCopilot.getState().loadBackends()

    expect(useCopilot.getState().selectedAgentKind).toBe('')
  })

  it('拉取失败静默：保留上次清单与选择，不写 lastError', async () => {
    useCopilot.setState({ backends: [option('pi'), option('dsh')], selectedAgentKind: 'dsh' })
    vi.mocked(copilotApi.fetchBackends).mockRejectedValue(new Error('net'))

    await useCopilot.getState().loadBackends()

    const s = useCopilot.getState()
    expect(s.backends.map((b) => b.kind)).toEqual(['pi', 'dsh'])
    expect(s.selectedAgentKind).toBe('dsh')
    expect(s.lastError).toBeNull()
    // 但**不再完全静默**：状态位要能让切换器说出「没拉到 + 重试」，
    // 而不是把「慢/失败」显示成「后端清单暂不可用」并永不重试（2026-11-27 现场）。
    expect(s.backendsState).toBe('error')
  })

  it('拉取成功把状态置 ready（切换器据此不再显示加载中）', async () => {
    useCopilot.setState({ backends: [], backendsState: 'idle' })
    vi.mocked(copilotApi.fetchBackends).mockResolvedValue([option('pi')])

    await useCopilot.getState().loadBackends()

    expect(useCopilot.getState().backendsState).toBe('ready')
  })

  it('在飞时不重复发请求（菜单每次打开都可能触发重拉）', async () => {
    useCopilot.setState({ backendsState: 'loading' })
    const spy = vi.mocked(copilotApi.fetchBackends)
    spy.mockClear()

    await useCopilot.getState().loadBackends()

    expect(spy).not.toHaveBeenCalled()
  })
})

describe('copilot store：后端选择', () => {
  it('选中可用后端并持久化', () => {
    useCopilot.setState({ backends: [option('pi'), option('dsh')], selectedAgentKind: 'pi' })

    useCopilot.getState().selectAgentKind('dsh')

    expect(useCopilot.getState().selectedAgentKind).toBe('dsh')
    expect(localStorage.getItem('copilot:agent-kind')).toBe('dsh')
  })

  it('不可用的后端选不中（保持原选择）', () => {
    useCopilot.setState({ backends: [option('pi'), option('dsh', false, '未配置可用的 LLM 平台')], selectedAgentKind: 'pi' })

    useCopilot.getState().selectAgentKind('dsh')

    expect(useCopilot.getState().selectedAgentKind).toBe('pi')
  })

  it('清单里没有的 kind 选不中', () => {
    useCopilot.setState({ backends: [option('pi')], selectedAgentKind: 'pi' })

    useCopilot.getState().selectAgentKind('typo')

    expect(useCopilot.getState().selectedAgentKind).toBe('pi')
  })

  it('登出清空选择（清单保留：部署级信息不随账号变）', () => {
    useCopilot.setState({ backends: [option('pi')], selectedAgentKind: 'dsh' })
    localStorage.setItem('copilot:agent-kind', 'dsh')

    useCopilot.getState().reset()

    expect(useCopilot.getState().selectedAgentKind).toBe('')
    expect(useCopilot.getState().backends.map((b) => b.kind)).toEqual(['pi'])
    expect(localStorage.getItem('copilot:agent-kind')).toBeNull()
  })
})

describe('copilot store：新会话带上所选后端', () => {
  const emptyStream = () =>
    vi.mocked(copilotApi.openMessageStream).mockImplementation(() =>
      Promise.resolve(sseResponse(['data: {"type":"done","session_id":"s-1"}\n\n'])),
    )

  /**
   * 会话归属由**本轮勾选**推导（见 store/turn.ts）：勾 1 个归它、勾 2 个以上归第一
   * 个（顺序 = 栏的左右顺序）、一个都不勾才用 `selectedAgentKind`。
   *
   * 断言第三个实参（= agent_kind）而不是内部变量：这三态错了不会报错，只会在整段
   * 会话里一直用错后端。
   */
  const ownerKindArg = () => vi.mocked(copilotApi.createSession).mock.calls[0]![2]

  it('send 建会话时把 selectedAgentKind 作为 agent_kind 下发', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    emptyStream()
    useCopilot.setState({ backends: [option('pi'), option('dsh')], selectedAgentKind: 'dsh' })

    await useCopilot.getState().send('你好')

    expect(copilotApi.createSession).toHaveBeenCalledWith('', undefined, 'dsh')
  })

  it('未选择时传空串（后端走默认 pi，不在前端硬编码）', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    emptyStream()

    await useCopilot.getState().send('你好')

    expect(copilotApi.createSession).toHaveBeenCalledWith('', undefined, '')
  })

  it('勾 1 个：会话归属就是它（本轮唯一参与者）', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    emptyStream()
    useCopilot.setState({
      backends: [option('pi'), option('dsh')],
      selectedAgentKind: 'pi',
      answerAgents: ['dsh'],
    })

    await useCopilot.getState().send('你好')

    expect(ownerKindArg()).toBe('dsh')
  })

  it('勾 2 个：会话归第一个（顺序 = 栏的左右顺序，与栏头一致）', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    emptyStream()
    useCopilot.setState({
      backends: [option('pi'), option('dsh')],
      selectedAgentKind: 'pi',
      answerAgents: ['dsh', 'pi'],
    })

    await useCopilot.getState().send('你好')

    expect(ownerKindArg()).toBe('dsh')
  })

  it('一个都不勾：会话归 selectedAgentKind（部署默认）', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    emptyStream()
    useCopilot.setState({
      backends: [option('pi'), option('dsh')],
      selectedAgentKind: 'dsh',
      answerAgents: [],
    })

    await useCopilot.getState().send('你好')

    expect(ownerKindArg()).toBe('dsh')
  })

  it('勾了不可用（缺 SDK）的后端：它不会成为会话归属，回落到本轮真实参与者', async () => {
    vi.mocked(copilotApi.createSession).mockResolvedValue(session)
    emptyStream()
    useCopilot.setState({
      backends: [option('pi'), option('dsh', false, '未安装 DeepSeek Harness SDK')],
      selectedAgentKind: 'pi',
      // 用户先勾了不可用的 dsh 再勾 pi：dsh 连栏都不会出现，更不该是会话归属
      answerAgents: ['dsh', 'pi'],
    })

    await useCopilot.getState().send('你好')

    expect(ownerKindArg()).toBe('pi')
  })

  it('已有会话不重建、不换后端（agent_kind 会话级不可换）', async () => {
    emptyStream()
    useCopilot.setState({ sessionId: 's-9', selectedAgentKind: 'dsh' })

    await useCopilot.getState().send('继续')

    expect(copilotApi.createSession).not.toHaveBeenCalled()
    // 第 4 个参数是本轮参与的 agent 清单（默认空 = 单跑会话默认后端）
    expect(copilotApi.openMessageStream).toHaveBeenCalledWith('s-9', '继续', expect.anything(), [])
  })
})

describe('copilot store：后端工具函数', () => {
  it('findBackend 按 kind 取项，找不到返回 undefined', () => {
    expect(findBackend([option('pi')], 'pi')?.label).toBe('Pi')
    expect(findBackend([option('pi')], 'dsh')).toBeUndefined()
  })

  it('defaultAgentKind 取第一项，空清单返回空串（由后端定默认）', () => {
    expect(defaultAgentKind([option('dsh'), option('pi')])).toBe('dsh')
    expect(defaultAgentKind([])).toBe('')
  })

  it('resolveCapabilities 取该后端声明的能力（UI 据此隐藏插话框等）', () => {
    expect(resolveCapabilities([option('pi'), option('dsh')], 'dsh').steer).toBe(false)
    expect(resolveCapabilities([option('pi')], 'pi').steer).toBe(true)
  })

  it('resolveCapabilities 对未知名/空清单回落到保守缺省（按 pi 放行）', () => {
    expect(resolveCapabilities([], 'pi')).toBe(DEFAULT_CAPABILITIES)
    expect(resolveCapabilities([option('pi')], 'gone')).toBe(DEFAULT_CAPABILITIES)
    // 缺省不能是「全 false」：那会让插话框在每次冷启动先消失一下
    expect(DEFAULT_CAPABILITIES.steer).toBe(true)
  })
})
