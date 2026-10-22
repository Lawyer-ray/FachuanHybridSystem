import { describe, expect, it } from 'vitest'

import {
  estimateTokens,
  historyToMessages,
  parseSseEvent,
  previewToolArgs,
  shortToolName,
  takeSseFrames,
  tokensPerSecond,
} from './domain'
import type { AgentHistoryMessage } from './types'

describe('takeSseFrames', () => {
  it('完整帧切出、半截留作 rest', () => {
    const { frames, rest } = takeSseFrames('data: {"type":"meta"}\n\ndata: {"type":"del')
    expect(frames).toEqual(['data: {"type":"meta"}'])
    expect(rest).toBe('data: {"type":"del')
  })

  it('跨 chunk 拼回后半截变完整帧', () => {
    const first = takeSseFrames('data: {"type":"a')
    const merged = first.rest + 'ta"}\n\n'
    const { frames, rest } = takeSseFrames(merged)
    expect(frames).toEqual(['data: {"type":"ata"}'])
    expect(rest).toBe('')
  })

  it('多帧一次取出（真机线上格式）', () => {
    const wire = 'data: {"type": "delta", "content": "你好"}\n\ndata: {"type": "done"}\n\n'
    const { frames, rest } = takeSseFrames(wire)
    expect(frames).toHaveLength(2)
    expect(rest).toBe('')
  })

  it('帧尾容忍 CR（行尾为 CRLF 的帧也能解析；后端实际只发 LF）', () => {
    const { frames } = takeSseFrames('data: {"type":"done"}\r\n\n')
    expect(frames).toEqual(['data: {"type":"done"}\r'])
    expect(parseSseEvent(frames[0] ?? '')).toEqual({ type: 'done' })
  })
})

describe('parseSseEvent', () => {
  it('解析 data 帧为事件对象', () => {
    expect(parseSseEvent('data: {"type":"delta","content":"A"}')).toEqual({ type: 'delta', content: 'A' })
  })

  it('坏 JSON / 无 data 前缀 / 缺 type 字段一律返回 null', () => {
    expect(parseSseEvent('data: {oops')).toBeNull()
    expect(parseSseEvent('event: ping\nid: 1')).toBeNull()
    expect(parseSseEvent('data: "纯字符串"')).toBeNull()
  })
})

describe('historyToMessages', () => {
  const rows: AgentHistoryMessage[] = [
    { message_id: 1, role: 'user', content: '问', tool_name: '', created_at: '', metadata: {} },
    { message_id: 2, role: 'assistant', content: '答', tool_name: '', created_at: '', metadata: { truncated: true } },
    { message_id: 3, role: 'tool', content: 'x'.repeat(3000), tool_name: 'mcp__fachuan__list_cases', created_at: '', metadata: {} },
  ]

  it('role/content 映射 + truncated 透传', () => {
    const messages = historyToMessages(rows)
    expect(messages.map((m) => m.role)).toEqual(['user', 'assistant', 'tool'])
    expect(messages[1]?.truncated).toBe(true)
    expect(messages[0]?.truncated).toBeUndefined()
  })

  it('工具结果预览截到 2000 字符', () => {
    expect(historyToMessages(rows)[2]?.content).toHaveLength(2000)
  })
})

describe('展示归一', () => {
  it('shortToolName 去掉 mcp 前缀，空名兜底', () => {
    expect(shortToolName('mcp__fachuan__delete_case')).toBe('delete_case')
    expect(shortToolName('list_cases')).toBe('list_cases')
    expect(shortToolName(undefined)).toBe('工具')
  })

  it('previewToolArgs 空对象为空串、超长截断', () => {
    expect(previewToolArgs({})).toBe('')
    expect(previewToolArgs({ a: 1 })).toBe('{"a":1}')
    expect(previewToolArgs({ k: 'x'.repeat(200) }, 50).endsWith('…')).toBe(true)
  })
})

describe('输出速度估算', () => {
  it('estimateTokens：CJK 约 0.7/字，ASCII 约 4 字符/token', () => {
    expect(estimateTokens('你好')).toBe(1) // 2 字 × 0.7 = 1.4 → 1
    expect(estimateTokens('abcdefgh')).toBe(2) // 8/4
    expect(estimateTokens('你好abcdefgh')).toBe(3) // 1.4 + 2 ≈ 3
    expect(estimateTokens('')).toBe(0)
  })

  it('tokensPerSecond：滑动窗口内按采样斜率计算', () => {
    const now = 10_000
    const samples: Array<[number, number]> = [
      [now - 3000, 0],
      [now - 2000, 10],
      [now - 1000, 20],
      [now, 30],
    ]
    // 窗口起点取第一个 >= now-2000 的采样（10 tokens），2 秒 +20
    expect(tokensPerSecond(samples, now)).toBeCloseTo(10, 5)
  })

  it('样本不足或时间倒挂时为 0', () => {
    expect(tokensPerSecond([], Date.now())).toBe(0)
    expect(tokensPerSecond([[1000, 5]], Date.now())).toBe(0)
  })
})
