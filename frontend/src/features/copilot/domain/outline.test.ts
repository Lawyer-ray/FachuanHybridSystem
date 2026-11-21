import { describe, expect, it } from 'vitest'

import type { ChatMessage } from '../types'
import { buildTurnOutline } from './outline'

function message(over: Partial<ChatMessage> & Pick<ChatMessage, 'id' | 'role'>): ChatMessage {
  return { content: '', ...over }
}

describe('buildTurnOutline：轮次归属', () => {
  it('多答归一轮：user 之后的 assistant/tool 都属于同一轮', () => {
    const outline = buildTurnOutline([
      message({ id: 'u1', role: 'user', content: '问题一', createdAt: 1000 }),
      message({ id: 'a1', role: 'assistant', agentKind: 'pi', content: '回答一' }),
      message({ id: 't1', role: 'tool', agentKind: 'dsh', content: '工具结果' }),
      message({ id: 'a2', role: 'assistant', agentKind: 'dsh', content: '回答二' }),
    ])
    expect(outline).toEqual([
      { turn: 1, promptId: 'u1', answerId: 'a1', preview: '问题一', at: 1000, agents: ['pi', 'dsh'] },
    ])
  })

  it('父子关系：每条 user 开启一轮，answerId 指向该轮第一条回答', () => {
    const outline = buildTurnOutline([
      message({ id: 'u1', role: 'user', content: '问题一' }),
      message({ id: 'a1', role: 'assistant', agentKind: 'pi', content: '回答一' }),
      message({ id: 't1', role: 'tool', content: '工具' }),
      message({ id: 'u2', role: 'user', content: '问题二' }),
      message({ id: 'a2', role: 'assistant', agentKind: 'dsh', content: '回答二' }),
    ])
    expect(outline.map((item) => ({ turn: item.turn, promptId: item.promptId, answerId: item.answerId }))).toEqual([
      { turn: 1, promptId: 'u1', answerId: 'a1' },
      { turn: 2, promptId: 'u2', answerId: 'a2' },
    ])
  })

  it('failed 空回答不当锚点；整轮只有工具时 answerId 缺省', () => {
    const outline = buildTurnOutline([
      message({ id: 'u1', role: 'user', content: '问题' }),
      message({ id: 'a1', role: 'assistant', agentKind: 'dsh', failed: true, content: '' }),
      message({ id: 'a2', role: 'assistant', agentKind: 'pi', content: '真回答' }),
      message({ id: 'u2', role: 'user', content: '再问' }),
      message({ id: 't1', role: 'tool', content: '只有工具' }),
    ])
    expect(outline[0]?.answerId).toBe('a2')
    expect(outline[0]?.agents).toEqual(['dsh', 'pi'])
    expect(outline[1]?.answerId).toBeUndefined()
  })

  it('窗口从轮次中间开始：前导 assistant/tool 没有提问可跳，忽略', () => {
    const outline = buildTurnOutline([
      message({ id: 'a0', role: 'assistant', content: '上一页的尾巴' }),
      message({ id: 't0', role: 'tool', content: '上一页的工具' }),
      message({ id: 'u1', role: 'user', content: '本页第一条提问' }),
      message({ id: 'a1', role: 'assistant', content: '回答' }),
    ])
    expect(outline).toHaveLength(1)
    expect(outline[0]?.promptId).toBe('u1')
  })
})

describe('buildTurnOutline：preview 截断', () => {
  it('换行归一为空格并 trim', () => {
    const outline = buildTurnOutline([message({ id: 'u1', role: 'user', content: '第一行\n  第二行\t第三行  ' })])
    expect(outline[0]?.preview).toBe('第一行 第二行 第三行')
  })

  it('超过 40 字截断并补省略号（第 41 字起丢弃）', () => {
    const outline = buildTurnOutline([message({ id: 'u1', role: 'user', content: '问'.repeat(50) })])
    expect(outline[0]?.preview).toBe(`${'问'.repeat(40)}…`)
    expect([...(outline[0]?.preview ?? '')]).toHaveLength(41)
  })

  it('恰好 40 字不补省略号', () => {
    const outline = buildTurnOutline([message({ id: 'u1', role: 'user', content: '问'.repeat(40) })])
    expect(outline[0]?.preview).toBe('问'.repeat(40))
  })
})
