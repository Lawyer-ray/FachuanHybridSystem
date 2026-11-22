// @vitest-environment jsdom
/**
 * 单栏的工具密度：连续的 tool 消息收成**一条**可换行的 chip 带（jsdom）。
 *
 * 锁的是三件事，都是律师能直接感知的：
 * 1. **密度**：一串连续工具只占一个排版块（原来是每工具一行，16 条 = 16 行）；
 * 2. **顺序**：聚段只换排版，不重排、不跨消息合并——chip 带里的先后就是到达先后，
 *    chip 带与气泡的先后就是时间先后；
 * 3. **不吞消息**：工具夹在正文中间时，带子只覆盖这一段连续的工具，非工具消息照旧
 *    各走各的 `renderAnswer`。
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import type { ChatMessage } from '../types'
import { AnswerGroupView } from './AnswerGroupView'

const msg = (over: Partial<ChatMessage> & Pick<ChatMessage, 'id' | 'role'>): ChatMessage => ({
  content: '',
  ...over,
})

const toolMsg = (id: string, toolName: string): ChatMessage =>
  msg({ id, role: 'tool', toolName, content: `${toolName} 的结果`, toolState: 'ok' })

/** 替身：真实实现是 Bubble（Markdown / 放字 / 操作条），与本节要验的排版无关 */
const renderAnswer = (message: ChatMessage) => <div data-testid={`answer-${message.id}`}>{message.content}</div>

/** AnswerGroupView 返回 Fragment，它的子节点就是 render 容器的第一层子节点 */
const childrenOf = (container: HTMLElement): HTMLElement[] => Array.from(container.children) as HTMLElement[]

describe('AnswerGroupView 单栏：工具 chip 带', () => {
  it('连续 3 条工具只占一条 chip 带，换成一行放多枚', () => {
    const { container } = render(
      <AnswerGroupView
        answers={[toolMsg('t1', 'get_current_user'), toolMsg('t2', 'get_server_time'), toolMsg('t3', 'list_lawyers')]}
        renderAnswer={renderAnswer}
      />,
    )
    const children = childrenOf(container)

    expect(children).toHaveLength(1)
    const strip = children[0]!
    // 换行是这条带子的全部意义：没有 flex-wrap 就是「16 条工具一行一条」的老样子
    expect(strip.className).toContain('flex-wrap')
    const chips = [...strip.querySelectorAll('details')]
    expect(chips).toHaveLength(3)
    // 带内先后 = 到达先后
    expect(chips.map((chip) => chip.textContent)).toEqual([
      expect.stringContaining('get_current_user'),
      expect.stringContaining('get_server_time'),
      expect.stringContaining('list_lawyers'),
    ])
  })

  it('工具夹在正文之间：顺序不变，带子只覆盖那一段连续的工具', () => {
    const { container } = render(
      <AnswerGroupView
        answers={[
          msg({ id: 'a1', role: 'assistant', content: '先查一下' }),
          toolMsg('t1', 'get_current_user'),
          toolMsg('t2', 'get_server_time'),
          msg({ id: 'a2', role: 'assistant', content: '查完了' }),
          toolMsg('t3', 'list_lawyers'),
        ]}
        renderAnswer={renderAnswer}
      />,
    )
    const children = childrenOf(container)

    expect(children).toHaveLength(4)
    expect(children[0]!.dataset.testid).toBe('answer-a1')
    // 中间两条连续工具合成一条带子（不是两条）
    expect(children[1]!.querySelectorAll('details')).toHaveLength(2)
    expect(children[2]!.dataset.testid).toBe('answer-a2')
    // 后面那条工具与前面隔着一条正文，必须自成一条带子（不能跨消息合并）
    expect(children[3]!.querySelectorAll('details')).toHaveLength(1)
    expect(screen.getByTestId('answer-a2').textContent).toBe('查完了')
  })

  it('只有一条工具也走 chip 带（整轮只调了一个工具时不该又变回整行）', () => {
    const { container } = render(
      <AnswerGroupView answers={[toolMsg('t1', 'get_case')]} renderAnswer={renderAnswer} />,
    )

    const children = childrenOf(container)
    expect(children).toHaveLength(1)
    expect(children[0]!.querySelectorAll('details')).toHaveLength(1)
    expect(children[0]!.textContent).toContain('get_case')
  })
})
