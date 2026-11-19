// @vitest-environment jsdom
/**
 * 多答并排渲染（jsdom）。
 *
 * 必须成立的事实：
 * 1. **多答轮次**：2~4 条 assistant 各占一栏，各有栏头标明是谁（Pi / DeepSeek
 *    Harness）。没有栏头的话律师分不清几份意见出自谁，界面看起来就是「AI 说了
 *    几遍不同的话」；
 * 2. **单条轮次**：行为与引入本功能前**完全一致**——不加栏头、不包 grid，那是
 *    「本功能对现有体验零影响」的保证；
 * 3. **失败栏**：只标那一栏「本轮未做」，其他栏的正文照常显示。
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

describe('MessageList：多答并排', () => {
  it('两条 assistant 并排成两栏，各有栏头', () => {
    const { container } = renderWithMessages([
      { id: 'u1', role: 'user', content: '合同有效吗' },
      { id: 'a1', role: 'assistant', content: '主答正文', agentKind: 'pi' },
      { id: 'a2', role: 'assistant', content: '次答正文', agentKind: 'dsh' },
    ])
    stepAllFrames()

    // 两栏容器存在（grid）
    expect(screen.getByTestId('multi-answers')).toBeTruthy()
    // 栏头：律师要能一眼看出谁是谁
    expect(screen.getByText('Pi')).toBeTruthy()
    expect(screen.getByText('DeepSeek Harness')).toBeTruthy()
    // 两份正文都在（不是被合并成一份）
    expect(screen.getByText('主答正文')).toBeTruthy()
    expect(screen.getByText('次答正文')).toBeTruthy()
    expect(container.querySelectorAll('[data-testid^="multi-column-"]')).toHaveLength(2)
  })

  it('每栏按 agent 标明来源（data-testid 供定位，不依赖 DOM 顺序）', () => {
    renderWithMessages([
      { id: 'a1', role: 'assistant', content: '主答正文', agentKind: 'pi' },
      { id: 'a2', role: 'assistant', content: '次答正文', agentKind: 'dsh' },
    ])
    stepAllFrames()

    expect(screen.getByTestId('multi-column-pi').textContent).toContain('主答正文')
    expect(screen.getByTestId('multi-column-dsh').textContent).toContain('次答正文')
  })

  it('三栏：三个 agent 各一栏，栏数写进 data-columns（供布局类名选档）', () => {
    const { container } = renderWithMessages([
      { id: 'a1', role: 'assistant', content: '甲答', agentKind: 'pi' },
      { id: 'a2', role: 'assistant', content: '乙答', agentKind: 'dsh' },
      { id: 'a3', role: 'assistant', content: '丙答', agentKind: 'oai' },
    ])
    stepAllFrames()

    const grid = screen.getByTestId('multi-answers')
    expect(grid.getAttribute('data-columns')).toBe('3')
    expect(container.querySelectorAll('[data-testid^="multi-column-"]')).toHaveLength(3)
    for (const text of ['甲答', '乙答', '丙答']) expect(screen.getByText(text)).toBeTruthy()
    // 未知 kind 显示 kind 原文，不显示空白
    expect(screen.getByText('oai')).toBeTruthy()
  })

  it('四栏：上限仍能渲染（每栏都能分清是谁）', () => {
    const { container } = renderWithMessages([
      { id: 'a1', role: 'assistant', content: '答一', agentKind: 'pi' },
      { id: 'a2', role: 'assistant', content: '答二', agentKind: 'dsh' },
      { id: 'a3', role: 'assistant', content: '答三', agentKind: 'oai' },
      { id: 'a4', role: 'assistant', content: '答四', agentKind: 'gpt' },
    ])
    stepAllFrames()

    expect(screen.getByTestId('multi-answers').getAttribute('data-columns')).toBe('4')
    expect(container.querySelectorAll('[data-testid^="multi-column-"]')).toHaveLength(4)
  })

  it('默认后端的栏头被高亮（律师知道自己平时问的那个在哪）', () => {
    renderWithMessages([
      { id: 'a1', role: 'assistant', content: '主答', agentKind: 'pi' },
      { id: 'a2', role: 'assistant', content: '次答', agentKind: 'dsh' },
    ])
    stepAllFrames()

    // 默认后端 = 清单第一项；清单没拉到时按 pi 算（DEFAULT_AGENT_KIND）
    const piLabel = screen.getByText('Pi')
    const dshLabel = screen.getByText('DeepSeek Harness')
    expect(piLabel.getAttribute('data-default')).toBe('true')
    expect(dshLabel.getAttribute('data-default')).toBeNull()
  })

  it('失败那栏显示「本轮未做」，其他栏照常显示正文', () => {
    renderWithMessages([
      { id: 'a1', role: 'assistant', content: '主答正文', agentKind: 'pi' },
      { id: 'a2', role: 'assistant', content: '', agentKind: 'dsh', failed: true },
    ])
    stepAllFrames()

    expect(screen.getByText('主答正文')).toBeTruthy()
    // 失败栏不能是空白栏头：那看起来像「回答了但内容丢了」
    expect(screen.getByTestId('answer-failed').textContent).toContain('本轮未做')
    expect(screen.getByTestId('multi-column-dsh').textContent).toContain('本轮未做')
    expect(screen.getByTestId('multi-column-pi').textContent).not.toContain('本轮未做')
  })

  it('单条 assistant 不并排、不加栏头（与引入前完全一致）', () => {
    renderWithMessages([
      { id: 'u1', role: 'user', content: '问' },
      { id: 'a1', role: 'assistant', content: '单栏正文' },
    ])
    stepAllFrames()

    expect(screen.queryByTestId('multi-answers')).toBeNull()
    // 没有栏头：单栏时多一个「Pi」标签就是在暗示「本来可以有几栏」
    expect(screen.queryByText('Pi')).toBeNull()
    expect(screen.getByText('单栏正文')).toBeTruthy()
  })

  it('单栏失败轮次同样写「本轮未做」（不留在空的「（无内容）」）', () => {
    renderWithMessages([{ id: 'a1', role: 'assistant', content: '', agentKind: 'pi', failed: true }])
    stepAllFrames()

    // 不并排：单栏永远不加栏头
    expect(screen.queryByTestId('multi-answers')).toBeNull()
    // 但失败本身要说清：空正文的「（无内容）」读起来像 AI 回答了却没内容
    expect(screen.getByTestId('answer-failed').textContent).toContain('本轮未做')
    expect(screen.queryByText('（无内容）')).toBeNull()
  })

  it('历史回放的 agentKind 同样并排（刷新后多栏不塌成一段）', () => {
    // 与 store 的本地渲染同一判据：历史消息带着 agent_kind 也要分栏
    renderWithMessages([
      { id: 'db-1', role: 'user', content: '问' },
      { id: 'db-2', role: 'assistant', content: '历史主答', agentKind: 'pi' },
      { id: 'db-3', role: 'assistant', content: '历史次答', agentKind: 'dsh' },
      { id: 'db-4', role: 'assistant', content: '历史三答', agentKind: 'oai' },
    ])
    stepAllFrames()

    expect(screen.getByTestId('multi-answers')).toBeTruthy()
    expect(screen.getByText('历史主答')).toBeTruthy()
    expect(screen.getByText('历史次答')).toBeTruthy()
    expect(screen.getByText('历史三答')).toBeTruthy()
  })

  it('同一个 agent 的多段相邻回答合成一栏（不把一个人渲染成两栏）', () => {
    renderWithMessages([
      { id: 'u1', role: 'user', content: '问' },
      { id: 'a1', role: 'assistant', content: '前段', agentKind: 'pi' },
      { id: 'a2', role: 'assistant', content: '后段', agentKind: 'pi' },
      { id: 'a3', role: 'assistant', content: '次答', agentKind: 'dsh' },
    ])
    stepAllFrames()

    expect(screen.getByTestId('multi-answers')).toBeTruthy()
    // 两栏而不是三栏：pi 的两段拼成同一栏
    expect(screen.getByTestId('multi-column-pi').textContent).toContain('前段后段')
    expect(screen.getByTestId('multi-column-dsh').textContent).toContain('次答')
    expect(screen.getAllByText('Pi')).toHaveLength(1)
  })

  it('栏头写「agent · 模型」（律师靠它对比不同模型的效果）', () => {
    renderWithMessages([
      { id: 'a1', role: 'assistant', content: '主答', agentKind: 'pi', model: 'kimi-2.6' },
      { id: 'a2', role: 'assistant', content: '次答', agentKind: 'dsh', model: 'glm53' },
    ])
    stepAllFrames()

    expect(screen.getByTestId('multi-column-pi').textContent).toContain('Pi·kimi-2.6')
    expect(screen.getByTestId('multi-column-dsh').textContent).toContain('DeepSeek Harness·glm53')
    // 超长模型名靠 CSS 截断（max-w-[110px] truncate），全名留给 hover
    const model = screen.getAllByTestId('column-model')[0]!
    expect(model.getAttribute('title')).toBe('kimi-2.6')
    expect(model.className).toContain('max-w-[110px]')
    expect(model.className).toContain('truncate')
  })

  it('没带模型的栏只显示 agent 名（旧数据 / 未指定）', () => {
    renderWithMessages([
      { id: 'a1', role: 'assistant', content: '主答', agentKind: 'pi' },
      { id: 'a2', role: 'assistant', content: '次答', agentKind: 'dsh', model: 'glm53' },
    ])
    stepAllFrames()

    expect(screen.getByTestId('multi-column-pi').textContent).toContain('Pi')
    expect(screen.getByTestId('multi-column-pi').textContent).not.toContain('·')
    expect(screen.getByTestId('multi-column-dsh').textContent).toContain('·glm53')
  })

  it('单栏即使带了模型也不显示（避免噪音）', () => {
    renderWithMessages([{ id: 'a1', role: 'assistant', content: '单栏正文', agentKind: 'pi', model: 'kimi-2.6' }])
    stepAllFrames()

    expect(screen.queryByTestId('column-model')).toBeNull()
    expect(screen.queryByText('kimi-2.6')).toBeNull()
  })

  it('被用户消息隔开的两条 assistant 不并排（不是同一轮）', () => {
    renderWithMessages([
      { id: 'a1', role: 'assistant', content: '第一轮回答', agentKind: 'pi' },
      { id: 'u1', role: 'user', content: '第二个问题' },
      { id: 'a2', role: 'assistant', content: '第二轮回答', agentKind: 'dsh' },
    ])
    stepAllFrames()

    // 跨轮合并会把两个不相干的回答并排成「对照」，那是最糟的误读
    expect(screen.queryByTestId('multi-answers')).toBeNull()
  })
})
