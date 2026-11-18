// @vitest-environment jsdom
/**
 * 同题双答的并排渲染（jsdom）。
 *
 * 两个必须成立的事实：
 * 1. **双答轮次**：两条 assistant 并排成两栏，各有栏头标明是谁（Pi / DeepSeek
 *    Harness）。没有栏头的话律师分不清两份意见出自谁，界面看起来就是「AI 说了
 *    两遍不同的话」；
 * 2. **单条轮次**：行为与引入本功能前**完全一致**——不加栏头、不包 grid，那是
 *    「本功能对现有体验零影响」的保证。
 */

import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useCopilot } from '../store'
import type { ChatMessage } from '../types'
import { MessageList } from './MessageList'

/** 动画帧控制：useSmoothStreamText 用 rAF 逐拍放字，测试里同步推进 */
let rafQueue: FrameRequestCallback[] = []
let rafSeq = 0

beforeEach(() => {
  rafQueue = []
  rafSeq = 0
  vi.stubGlobal('requestAnimationFrame', (cb: FrameRequestCallback) => {
    rafQueue.push(cb)
    rafSeq += 1
    return rafSeq
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
  useCopilot.setState({ messages, streaming: false, loadingHistory: false, approvals: [], lastError: null })
  return render(<MessageList />)
}

describe('MessageList：同题双答并排', () => {
  it('两条 assistant 并排成两栏，各有栏头', () => {
    const { container } = renderWithMessages([
      { id: 'u1', role: 'user', content: '合同有效吗' },
      { id: 'a1', role: 'assistant', content: '主答正文', agentKind: 'pi' },
      { id: 'a2', role: 'assistant', content: '次答正文', agentKind: 'dsh' },
    ])
    stepAllFrames()

    // 两栏容器存在（grid）
    expect(screen.getByTestId('dual-answers')).toBeTruthy()
    // 栏头：律师要能一眼看出谁是谁
    expect(screen.getByText('Pi')).toBeTruthy()
    expect(screen.getByText('DeepSeek Harness')).toBeTruthy()
    // 两份正文都在（不是被合并成一份）
    expect(screen.getByText('主答正文')).toBeTruthy()
    expect(screen.getByText('次答正文')).toBeTruthy()
    expect(container.querySelectorAll('[data-testid^="dual-column-"]')).toHaveLength(2)
  })

  it('每栏按 agent 标明来源（data-testid 供定位，不依赖 DOM 顺序）', () => {
    renderWithMessages([
      { id: 'a1', role: 'assistant', content: '主答正文', agentKind: 'pi' },
      { id: 'a2', role: 'assistant', content: '次答正文', agentKind: 'dsh' },
    ])
    stepAllFrames()

    expect(screen.getByTestId('dual-column-pi').textContent).toContain('主答正文')
    expect(screen.getByTestId('dual-column-dsh').textContent).toContain('次答正文')
  })

  it('单条 assistant 不并排、不加栏头（与引入前完全一致）', () => {
    renderWithMessages([
      { id: 'u1', role: 'user', content: '问' },
      { id: 'a1', role: 'assistant', content: '单栏正文' },
    ])
    stepAllFrames()

    expect(screen.queryByTestId('dual-answers')).toBeNull()
    // 没有栏头：单栏时多一个「Pi」标签就是在暗示「本来可以有两个」
    expect(screen.queryByText('Pi')).toBeNull()
    expect(screen.getByText('单栏正文')).toBeTruthy()
  })

  it('历史回放的 agentKind 同样并排（刷新后两栏不塌成一段）', () => {
    // 与 store 的本地渲染同一判据：历史消息带着 agent_kind 也要分栏
    renderWithMessages([
      { id: 'db-1', role: 'user', content: '问' },
      { id: 'db-2', role: 'assistant', content: '历史主答', agentKind: 'pi' },
      { id: 'db-3', role: 'assistant', content: '历史次答', agentKind: 'dsh' },
    ])
    stepAllFrames()

    expect(screen.getByTestId('dual-answers')).toBeTruthy()
    expect(screen.getByText('历史主答')).toBeTruthy()
    expect(screen.getByText('历史次答')).toBeTruthy()
  })

  it('被用户消息隔开的两条 assistant 不并排（不是同一轮）', () => {
    renderWithMessages([
      { id: 'a1', role: 'assistant', content: '第一轮回答', agentKind: 'pi' },
      { id: 'u1', role: 'user', content: '第二个问题' },
      { id: 'a2', role: 'assistant', content: '第二轮回答', agentKind: 'dsh' },
    ])
    stepAllFrames()

    // 跨轮合并会把两个不相干的回答并排成「对照」，那是最糟的误读
    expect(screen.queryByTestId('dual-answers')).toBeNull()
  })
})
