// @vitest-environment jsdom
/**
 * 「还在干活」的可见反馈（jsdom）。
 *
 * 真实反馈（三栅截图）：Pi 2.4 秒就出字，dsh / openai-agents 憋到 16 秒才吐全文，
 * 律师看到的是「三个 agent 速度不一样」/「这两个卡死了」。根因是它们先调工具、
 * 调完才说正文，期间界面空白。必须成立的事实：
 *
 * 1. 工具在跑、正文没到时，**气泡内**（不是气泡外）有一行「正在查 XX…」；
 * 2. 正文一到就撤——不能出现「正文 + 正在查 XX」这种已不成立的叙述；
 * 3. 工具条只有一个可见位置：流式中在气泡内活动行，正文到达后收成气泡下 chip，
 *    绝不重复渲染成两处；
 * 4. 多栏里某一栏还在跑时显示当前动作，而不是「（无内容）」那个失败态文案。
 */

import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useCopilot } from '../store'
import type { ChatMessage } from '../types'
import { MessageList } from './MessageList'

/** useSmoothStreamText 用 rAF 逐拍放字，测试里同步推进（同 MessageList.dom.test） */
let rafQueue: FrameRequestCallback[] = []

beforeEach(() => {
  rafQueue = []
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    rafQueue.push(cb)
    return rafQueue.length
  })
  vi.stubGlobal('cancelAnimationFrame', () => {
    rafQueue = []
  })
})

afterEach(() => {
  vi.unstubAllGlobals()
  act(() => {
    useCopilot.setState({ messages: [], streaming: false, loadingHistory: false, approvals: [], lastError: null })
  })
})

function stepAllFrames(maxFrames = 400) {
  for (let i = 0; i < maxFrames; i += 1) {
    const pending = rafQueue
    rafQueue = []
    if (pending.length === 0) return
    act(() => {
      for (const cb of pending) cb(0)
    })
  }
}

function renderWithMessages(messages: ChatMessage[]) {
  useCopilot.setState({ messages, streaming: true, loadingHistory: false, approvals: [], lastError: null })
  return render(<MessageList />)
}

const tool = (id: string, name: string, content = '', agentKind?: string): ChatMessage => ({
  id,
  role: 'tool',
  content,
  toolName: name,
  ...(agentKind ? { agentKind } : {}),
})

describe('单栏：工具期间气泡内有可见反馈', () => {
  it('工具未返回时气泡内显示「正在查 XX…」（不是程序内部的工具名）', () => {
    // 单栏的工具行仍按时间平铺（那条路径的顺序本身就是对的），活动行看的是
    // 同一份 pending 工具：两者文案不同层——活动行说人话，工具行留原名可核对
    const pending = tool('t1', 'list_lawyers')
    renderWithMessages([
      { id: 'u1', role: 'user', content: '查下律师' },
      pending,
      { id: 'a1', role: 'assistant', content: '', streaming: true, tools: [pending] },
    ])

    const activity = screen.getByTestId('stream-activity')
    expect(activity.textContent).toContain('正在查律师名单…')
    expect(activity.textContent).not.toContain('list_lawyers')
    // 单栏的整行工具条仍在（不会因为多了活动行就消失）
    expect(document.body.textContent).toContain('调用中')
  })

  it('正文到达后活动行撤掉，只剩正文', () => {
    const { rerender } = renderWithMessages([{ id: 'a1', role: 'assistant', content: '', streaming: true }])
    useCopilot.setState({
      messages: [
        { id: 'a1', role: 'assistant', content: '结论如下', streaming: true },
      ],
    })
    rerender(<MessageList />)
    stepAllFrames()
    expect(screen.queryByTestId('stream-activity')).toBeNull()
    expect(screen.getByText('结论如下')).toBeTruthy()
  })
})

describe('多栏：空栏显示当前动作，不是「（无内容）」', () => {
  it('还在跑的那栏显示「正在查…」，不显示失败态文案', () => {
    renderWithMessages([
      { id: 'u1', role: 'user', content: '合同有效吗' },
      tool('t1', 'get_current_user', '', 'pi'),
      tool('t2', 'tool_search', '', 'dsh'),
      { id: 'a1', role: 'assistant', content: 'Pi 的答案', agentKind: 'pi', tools: [tool('t1', 'get_current_user', '', 'pi')] },
      { id: 'a2', role: 'assistant', content: '', agentKind: 'dsh', streaming: true, tools: [tool('t2', 'tool_search', '', 'dsh')] },
    ])
    stepAllFrames()

    expect(screen.getByTestId('multi-column-dsh').textContent).toContain('正在检索可用工具…')
    expect(screen.getByTestId('multi-column-dsh').textContent).not.toContain('（无内容）')
    expect(screen.getByTestId('multi-column-dsh').textContent).not.toContain('本轮未做')
    // 已出正文那一栏不该有活动行
    expect(screen.getByTestId('multi-column-pi').querySelector('[data-testid="stream-activity"]')).toBeNull()
  })

  it('工具行不再作为转录流独立项重复渲染（已归位的那些）', () => {
    const piTool = tool('t1', 'list_lawyers', '已查完', 'pi')
    renderWithMessages([
      { id: 'a1', role: 'assistant', content: 'Pi 的答案', agentKind: 'pi', tools: [piTool] },
      { id: 'a2', role: 'assistant', content: 'dsh 的答案', agentKind: 'dsh' },
    ])
    stepAllFrames()

    // 外面那条整行工具条（「已完成 · ...」）不该再出现——它已经在气泡下的 chip 里
    expect(screen.queryByText(/已完成 · /)).toBeNull()
    // chip 里仍能看到工具名（点开有返回值）
    expect(screen.getByTestId('multi-column-pi').textContent).toContain('list_lawyers')
  })
})
