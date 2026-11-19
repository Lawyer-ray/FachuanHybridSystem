/**
 * SSE 帧解析（纯函数，node 环境直接单测）。
 *
 * 与 streaming.ts（帧消费 / 流生命周期）配对：这里只负责「字节流 → 事件对象」
 * 的纯变换，fetch/reader/重连一律不进本模块。
 */

import type { AgentStreamEvent } from '../types'

let localIdSeed = 0
/** 本地气泡 id（历史消息沿用后端 message_id，流式期间的本地消息用递增 id） */
export function nextLocalId(): string {
  localIdSeed += 1
  return `local-${localIdSeed}`
}

/**
 * 从缓冲区里切出完整的 SSE 帧，返回剩余半截。
 *
 * 线上格式（backend agent_api._sse）：`data: {json}\n\n`。
 * 网络分块与帧边界无关：调用方把每次 chunk 追加进 buffer，再交给本函数；
 * 帧内可能夹 CRLF（容忍），行首无 `data: ` 前缀的行按 SSE 规范忽略。
 */
export function takeSseFrames(buffer: string): { frames: string[]; rest: string } {
  const frames: string[] = []
  let rest = buffer
  for (;;) {
    // 分隔符容忍 CRLF：反代/网关把 `\n\n` 改写成 `\r\n\r\n` 的情况真实存在，
    // 只认 `\n\n` 会让整条流一帧都切不出来（看着像「后端没回数据」）
    const match = /\r?\n\r?\n/.exec(rest)
    if (!match) break
    frames.push(rest.slice(0, match.index))
    rest = rest.slice(match.index + match[0].length)
  }
  return { frames, rest }
}

/** 单帧 → 事件对象；空帧/非 data 帧/坏 JSON 一律返回 null（容错跳过，流不断）。 */
export function parseSseEvent(frame: string): AgentStreamEvent | null {
  const dataLines = frame
    .split(/\r?\n/)
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice(5).trimStart())
  if (dataLines.length === 0) return null
  try {
    const parsed = JSON.parse(dataLines.join('\n')) as AgentStreamEvent
    return typeof parsed?.type === 'string' ? parsed : null
  } catch {
    return null
  }
}
