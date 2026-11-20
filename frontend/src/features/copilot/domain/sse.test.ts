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
    // CRLF 分隔符整块切掉：帧里不残留 CR，JSON.parse 与原逻辑结果一致
    expect(frames).toEqual(['data: {"type":"done"}'])
    expect(parseSseEvent(frames[0] ?? '')).toEqual({ type: 'done' })
  })

  it('整条流都是 CRLF 分隔符时也能逐帧切出（反代会把 `\\n\\n` 改写成 `\\r\\n\\r\\n`）', () => {
    // 早先只认 `\n\n`：整条流一帧都切不出来，表现像「后端什么都没回」
    const wire = 'data: {"type":"delta","content":"A"}\r\n\r\ndata: {"type":"done"}\r\n\r\n'
    const { frames, rest } = takeSseFrames(wire)
    expect(frames).toEqual(['data: {"type":"delta","content":"A"}', 'data: {"type":"done"}'])
    expect(rest).toBe('')
  })

  it('EOF 尾帧（没有空行结尾）留在 rest 里，调用方直接解析就能交付', () => {
    // 服务端写完最后一帧就关流、不补 `\n\n` 是常见行为。尾帧可能是最后一截正文、
    // 也可能是 done——早先直接丢掉，于是正常的轮次被当成断流。这里钉住契约：
    // 完整帧照常从 frames 出，尾巴原样留在 rest 里（streaming.ts 负责再解析一次）。
    const { frames, rest } = takeSseFrames('data: {"type":"delta","content":"半"}\n\ndata: {"type":"usage","output_tokens":12}')
    expect(frames).toEqual(['data: {"type":"delta","content":"半"}'])
    expect(parseSseEvent(rest)).toEqual({ type: 'usage', output_tokens: 12 })

    const tailDelta = takeSseFrames('data: {"type":"delta","content":"最后一句"}')
    expect(tailDelta.frames).toEqual([])
    expect(parseSseEvent(tailDelta.rest)).toEqual({ type: 'delta', content: '最后一句' })
  })

  it('注释行/心跳行不产生假事件（SSE 规范里 `:` 开头是注释）', () => {
    // 后端与反代都可能插 `:heartbeat` / `: ping`：它们没有 data 前缀，
    // 若被当成事件解析，轻则每几秒多一次无意义分发，重则被当成断流信号
    const wire = ':heartbeat\n\nretry: 3000\n\ndata: {"type":"delta","content":"正文"}\n\n'
    const { frames } = takeSseFrames(wire)
    expect(frames).toHaveLength(3)
    expect(frames.map((f) => parseSseEvent(f))).toEqual([null, null, { type: 'delta', content: '正文' }])
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
