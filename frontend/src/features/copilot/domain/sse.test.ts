import { describe, expect, it } from 'vitest'

import { parseSseEvent, takeSseFrames } from './sse'

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
