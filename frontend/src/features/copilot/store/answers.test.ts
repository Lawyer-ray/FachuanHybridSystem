/**
 * 「这个会话用哪个模型」的记忆（node 环境 + 假 localStorage）。
 *
 * 用户报的问题很具体：**刷新一次，模型选择就没了**。修复由两段组成，两条都必须成立：
 *
 * 1. **本地按会话记住**（`setAnswerModel` → localStorage，`hydrateAnswerModels` 装回）：
 *    管「刚选还没跑」的那一小段；
 * 2. **服务端兜底**（`seedAnswerModel` ← `AgentSession.llm_model`）：管跨浏览器/换设备。
 *
 * 顺序不能反：`seedAnswerModel` **只补空位**。律师手选过就必须尊重手选——否则刷新
 * 一次就被"纠正"回上一轮的模型，比不记住更糟。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

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

import { useCopilot } from './index'

/** 最小 localStorage（node 环境可能没有；持久化层对缺失静默降级，这里要验有值的情况） */
function installLocalStorage(): void {
  const map = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, String(value)),
    removeItem: (key: string) => void map.delete(key),
    clear: () => map.clear(),
  })
}

beforeEach(() => {
  installLocalStorage()
  useCopilot.setState({ sessionId: null, answerModels: {} })
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('模型选择的记忆', () => {
  it('选完即落盘，换个会话再切回来还在', () => {
    useCopilot.setState({ sessionId: 's1', answerModels: {} })
    useCopilot.getState().setAnswerModel('qoder', 'fachuan-gw/kimi-2.6')
    expect(useCopilot.getState().answerModels).toEqual({ qoder: 'fachuan-gw/kimi-2.6' })

    // 切到 s2：它没选过 → 空
    useCopilot.getState().hydrateAnswerModels('s2')
    expect(useCopilot.getState().answerModels).toEqual({})

    // 切回 s1：装回来
    useCopilot.getState().hydrateAnswerModels('s1')
    expect(useCopilot.getState().answerModels).toEqual({ qoder: 'fachuan-gw/kimi-2.6' })
  })

  it('取消指定（空串）也会把落盘清掉，避免下次又冒出旧模型', () => {
    useCopilot.setState({ sessionId: 's1', answerModels: {} })
    useCopilot.getState().setAnswerModel('qoder', 'Auto')
    useCopilot.getState().setAnswerModel('qoder', '')
    useCopilot.getState().hydrateAnswerModels('s1')
    expect(useCopilot.getState().answerModels).toEqual({})
  })

  it('服务端 llm_model 只补空位，不覆盖律师的手选', () => {
    useCopilot.setState({ sessionId: 's1', answerModels: {} })
    useCopilot.getState().seedAnswerModel('qoder', 'Auto')
    expect(useCopilot.getState().answerModels).toEqual({ qoder: 'Auto' })

    useCopilot.getState().setAnswerModel('qoder', 'fachuan-gw/kimi-2.6')
    useCopilot.getState().seedAnswerModel('qoder', 'Ultimate')
    expect(useCopilot.getState().answerModels).toEqual({ qoder: 'fachuan-gw/kimi-2.6' })
  })

  it('新对话用固定键：还没建会话时选中也要记住', () => {
    useCopilot.setState({ sessionId: null, answerModels: {} })
    useCopilot.getState().setAnswerModel('pi', 'kimi-2.6')
    useCopilot.getState().hydrateAnswerModels(null)
    expect(useCopilot.getState().answerModels).toEqual({ pi: 'kimi-2.6' })
  })
})
