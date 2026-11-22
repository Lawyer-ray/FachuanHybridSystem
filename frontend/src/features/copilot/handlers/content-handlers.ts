/**
 * 正文侧的事件处理器：思考累积、正文增量（连带用量采样）、引用表合并。
 *
 * 三者都写**消息**（而不是 store 的其他切片），所以归一处；共同的前置条件也相同：
 * 先按事件的 agent 找到目标气泡（`ctx.targetOf`），再只改那一条。
 */

import { estimateTokens, mergeCitations } from '../domain'
import { markLaneDelta, withDeltaSample } from '../domain/lane-stats'
import { emptyTurnStats } from '../domain/usage'
import type { StreamHandlers } from '../streaming'
import type { TurnHandlerContext } from './context'

export function createContentHandlers(
  ctx: TurnHandlerContext,
): Pick<StreamHandlers, 'onThinking' | 'onDelta' | 'onCitations'> {
  const { set, targetOf } = ctx

  const onThinking: StreamHandlers['onThinking'] = (chunk, origin) => {
    if (!chunk) return
    const targetId = targetOf(origin.kind)
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === targetId ? { ...m, thinking: (m.thinking ?? '') + chunk } : m,
      ),
    }))
  }

  const onDelta: StreamHandlers['onDelta'] = (chunk, origin) => {
    if (!chunk) return
    const targetId = targetOf(origin.kind)
    const now = Date.now()
    const est = estimateTokens(chunk)
    // **一次 set 写三处**（正文/该栏账/全局账）。原先一个 delta 要写三次 store，
    // 而每次写入都会跑一遍 `messages.map`——长会话里这是流式掉帧的主要来源之一。
    set((s) => ({
      messages: s.messages.map((m) =>
        // 首个正文 delta 到达 → 思考阶段结束（供前端收起/打勾）
        m.id === targetId ? { ...m, content: m.content + chunk, thinkingDone: true } : m,
      ),
      turnStats: withDeltaSample(s.turnStats, est, now),
      turnStatsByLane: {
        ...s.turnStatsByLane,
        [origin.kind]: markLaneDelta(s.turnStatsByLane[origin.kind] ?? emptyTurnStats(), est, now),
      },
    }))
  }

  // 引用表落在**该栏自己的**气泡上：多答时两栏可能引完全不同的材料，写死主栏会让
  // B 栏那句「见[K1]」点开的是 A 栏的证据。与正文/工具行走同一张路由表（targetOf），
  // 单栏时它回落默认气泡，口径与引入多答前一致。
  //
  // 写进气泡本身就是「流内缓存」：这一轮的正文在收尾落库前只活在这里，角标要能立刻
  // 点开就只能挑这条消息；刷新后另由 metadata.citations 重建（见
  // domain/transcript.historyToMessages）。同 citeNo 后到为准，见 mergeCitations
  // （增量事件可能先给名字、后补页码/原文）。
  const onCitations: StreamHandlers['onCitations'] = (citations, origin) => {
    if (citations.length === 0) return
    const targetId = targetOf(origin.kind)
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === targetId ? { ...m, citations: mergeCitations(m.citations, citations) } : m,
      ),
    }))
  }

  return { onThinking, onDelta, onCitations }
}
