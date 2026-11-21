// @vitest-environment jsdom
/**
 * 轮次大纲（TurnRail）接进转录后的行为（jsdom）。
 *
 * 锁三条口径，都是「不说就会误导航」的：
 * 1. **门槛**：上翻超过 60px 且 ≥4 轮才出现——贴着底看实时输出时给一条竖条只是噪声，
 *    两三轮的短会话更不需要；
 * 2. **锚点是用户提问**：每轮的 `[data-prompt-id]` 必须落在 user 消息那一组上，
 *    否则「跳到第 3 轮」会落到上一轮的答案里；
 * 3. **跳转不改 store、不改流式状态**：只做 scrollIntoView（组件不猜转录结构）。
 */

import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useCopilot } from '../store'
import type { ChatMessage } from '../types'
import { MessageList } from './MessageList'

/** rAF 手动推进：rail 的度量是 rAF 合帧的，测试里同步跑更稳 */
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
  vi.restoreAllMocks()
})

function flushFrames() {
  const pending = rafQueue
  rafQueue = []
  act(() => {
    for (const cb of pending) cb(0)
  })
}

/** 造 n 轮（每轮 user + 一条 assistant） */
function makeTurns(n: number): ChatMessage[] {
  const messages: ChatMessage[] = []
  for (let i = 1; i <= n; i += 1) {
    messages.push({ id: `u${i}`, role: 'user', content: `第 ${i} 个问题` })
    messages.push({ id: `a${i}`, role: 'assistant', content: `第 ${i} 个回答` })
  }
  return messages
}

function setup(messages: ChatMessage[]) {
  useCopilot.setState({ messages, streaming: false, loadingHistory: false, approvals: [], lastError: null })
  const view = render(<MessageList />)
  return view
}

/** 把滚动容器伪装成「已上翻 offset px」并触发一次 scroll */
function scrollTo(offset: number) {
  const el = document.querySelector('[data-copilot-scroll]') as HTMLDivElement
  Object.defineProperty(el, 'scrollTop', { value: offset, configurable: true, writable: true })
  Object.defineProperty(el, 'scrollHeight', { value: 2000, configurable: true, writable: true })
  Object.defineProperty(el, 'clientHeight', { value: 600, configurable: true, writable: true })
  act(() => {
    el.dispatchEvent(new Event('scroll'))
  })
  flushFrames()
  return el
}

describe('轮次大纲：出现门槛', () => {
  it('≥4 轮且上翻超过 60px 才出现', () => {
    setup(makeTurns(4))
    expect(screen.queryByLabelText('轮次大纲')).toBeNull()

    scrollTo(200)
    expect(screen.getByLabelText('轮次大纲')).toBeTruthy()
    expect(screen.getAllByRole('listitem').length).toBeGreaterThanOrEqual(4)
  })

  it('贴着底部（不超过 60px）不出现：正在读实时输出时不该挡视线', () => {
    setup(makeTurns(4))
    scrollTo(30)
    expect(screen.queryByLabelText('轮次大纲')).toBeNull()
  })

  it('只有 3 轮时不出现：短会话给竖条只是噪声', () => {
    setup(makeTurns(3))
    scrollTo(400)
    expect(screen.queryByLabelText('轮次大纲')).toBeNull()
  })
})

describe('轮次大纲：锚点与跳转', () => {
  it('每轮的 data-prompt-id 落在**用户提问**那一组上', () => {
    setup(makeTurns(2))
    const prompts = Array.from(document.querySelectorAll<HTMLElement>('[data-prompt-id]'))
    expect(prompts.map((node) => node.dataset.promptId)).toEqual(['u1', 'u2'])
    // 锚点里应该是提问，不是回答
    expect(prompts[0]!.textContent).toContain('第 1 个问题')
  })

  it('点击某一轮只做 scrollIntoView，不动 store / 不改流式状态', () => {
    const spy = vi.fn()
    Element.prototype.scrollIntoView = spy
    setup(makeTurns(4))
    scrollTo(300)

    const target = screen.getByTitle(/第 3 轮/)
    act(() => {
      target.click()
    })

    expect(spy).toHaveBeenCalledTimes(1)
    expect(useCopilot.getState().streaming).toBe(false)
    expect(useCopilot.getState().messages).toHaveLength(8)
  })

  it('当前轮随滚动位置前移（aria-current 只落在一个按钮上）', () => {
    setup(makeTurns(4))
    // jsdom 里 getBoundingClientRect 全是 0，因此每一轮都在 80px 线内 → 取最后一轮
    scrollTo(300)
    const current = document.querySelectorAll('[aria-current="true"]')
    expect(current).toHaveLength(1)
    expect(current[0]!.getAttribute('title')).toContain('第 4 轮')
  })
})
