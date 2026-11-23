/**
 * 一轮的生命周期：用量记账、降级/失败、收尾判定，以及排队/压缩状态的退场清理。
 *
 * 共同点：它们改的都是**栏级/轮级**状态（`turnStats` / `turnStatsByLane` /
 * `queuePosition` / `compacting` / `lastError` / 哪些气泡还在流），而不是正文本身。
 *
 * `queuePosition` / `compacting` 在本文件只有**清理**、没有写入：写入端在
 * `handlers/approval-question.ts`（onQueued 记排队名次、onCompaction 记压缩阶段）。
 * 这里处理的两条退场路径是「事件永远不会再来」时唯一的清理时机：onProgress
 * （本轮开始推进，排队横幅该消失）与 onStreamEnd（断流时压缩 end 不会到达）。
 *
 * 收尾的难点全部写在 {@link createLaneLifecycleHandlers} 的 finishLane 里：多答时每栏
 * 各发一次 done，先跑完的那栏**不能**把其他栏一起收掉。
 */

import { addUsageToLane, addUsageToTurn } from '../domain/lane-stats'
import { emptyTurnStats } from '../domain/usage'
import type { StreamHandlers } from '../streaming'
import type { TurnStats } from '../types'
import type { TurnHandlerContext } from './context'

export function createLaneLifecycleHandlers(ctx: TurnHandlerContext): {
  handlers: Pick<
    StreamHandlers,
    'onUsage' | 'onProgress' | 'onStreamEnd' | 'onDegraded' | 'onError' | 'onDone'
  >
  finishAssistant: () => void
} {
  const { set, get, targetOf, columnCount } = ctx

  /** 收尾**全部**本轮的 assistant 气泡（多答各栏都要停住光标） */
  const finishAssistant = () => {
    set((s) => ({
      messages: s.messages.map((m) =>
        m.role === 'assistant' && m.streaming ? { ...m, streaming: false } : m,
      ),
    }))
  }

  /**
   * 排队横幅的退场清理（写入端在 `handlers/approval-question.ts` 的 onQueued）。
   * 仅在有值时才 set（避免每个 delta 都触发一次状态写入）。
   */
  const clearQueueBanner = () => {
    set((s) => (s.queuePosition !== null ? { queuePosition: null } : s))
  }

  /**
   * 写某一栏的用量账（`kind` 空串 = 单栏/未标注，仍单独成一份）。
   *
   * 为什么按 `kind` 而不是 run_id：`run_id` 恒为 `session:kind:1`、跨轮不递增
   * （后端尚未修），拿它当键会把两栏写进同一份账；`agent` 是每帧都带且真实
   * 互斥的（多答每栏一个后端）。
   */
  const bumpLane = (kind: string, fn: (lane: TurnStats) => TurnStats) => {
    set((s) => ({
      turnStatsByLane: {
        ...s.turnStatsByLane,
        [kind]: fn(s.turnStatsByLane[kind] ?? emptyTurnStats()),
      },
    }))
  }

  const onUsage: StreamHandlers['onUsage'] = (usage, origin) => {
    // 分栏账：多答的核心可比性（哪一栏贵、哪一栏缓存命中高）
    bumpLane(origin.kind, (lane) => addUsageToLane(lane, usage))
    set((s) => ({ turnStats: addUsageToTurn(s.turnStats, usage) }))
  }

  const onProgress = clearQueueBanner

  const onStreamEnd: StreamHandlers['onStreamEnd'] = () => {
    // `compacting` 只能靠 compaction end 事件退场；断流时那个事件永远不会来，
    // Composer 底栏就会永远写着「正在压缩上下文…」（压缩中途按停止即可复现）。
    // 与 `sawDone` 无关：正常结束走到这里时它早已是 false，多一次判断只会多一个分支。
    set((s) => (s.compacting ? { compacting: false } : s))
  }

  const onDegraded: StreamHandlers['onDegraded'] = (reason) => {
    // 后端降级（aux 席位已满）：本轮律师选了几家，实际只跑了一家。不说明的话
    // 他会以为对比没生效、或者其余几家的回答丢了。
    //
    // 同时要把**被丢下的那几栏**就地收尾并标「本轮未做」：后端收窄了 agents，
    // 只会给主栏发 done，其余栏永远等不到收尾信号——界面上就是一排转圈的空栏。
    // 主栏是 `targetOf('')`（路由表为空时它就是第一栏，见 store/turn-send.ts）。
    const keptId = targetOf('')
    set((s) => ({
      messages: s.messages.map((m) =>
        m.role === 'assistant' && m.streaming && m.id !== keptId
          ? { ...m, streaming: false, failed: true }
          : m,
      ),
      lastError: reason,
    }))
  }

  const onError: StreamHandlers['onError'] = (message, origin) => {
    // 多答时一个后端失败其他照常输出：错误行必须标明是哪一栏失败了，
    // 否则律师会以为整轮都没跑成，而屏幕上半截明明有答案。
    const who = columnCount > 1 && origin.kind ? `${origin.kind}：` : ''
    set({ lastError: `${who}${message}` })
    // 失败方的栏要停住光标并标成「本轮未做」；其他栏继续流（finishAssistant 会把
    // 所有 streaming 气泡收掉，这里只收失败那一栏）。
    //
    // 为什么明写「本轮未做」而不是留空：那一栏到收尾都没有正文，不标记的话界面上
    // 就是一个空白的栏头，看起来像「AI 回答了但内容丢了」。
    // 查不到时（本轮没登记过该 agent）回落到默认栏，不造孤儿气泡
    const failedId = targetOf(origin.kind)
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === failedId ? { ...m, streaming: false, failed: true } : m,
      ),
    }))
  }

  /**
   * 收这一栏，并判定整轮是否结束。
   *
   * **只收这一栏**，不能 `finishAssistant()`（那会收掉全部 streaming 气泡）。
   * 多答真实事故：pi 先完成 → done 到达 → 全部气泡被收掉 → dsh 后续的 delta 无处
   * 可写，界面上两栏都是「(无内容)」，并冒出一句「流处理异常」。单后端时
   * columnCount === 1，收这一栏等价于收全部，行为与原来一致。
   */
  const finishLane = (
    context: Parameters<StreamHandlers['onDone']>[0],
    origin: Parameters<StreamHandlers['onDone']>[1],
  ) => {
    const doneId = targetOf(origin.kind)
    const doneAt = Date.now()
    bumpLane(origin.kind, (lane) => ({ ...lane, doneAt }))
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === doneId && m.streaming ? { ...m, streaming: false } : m,
      ),
    }))
    // 整轮是否结束由「还有没有栏在流」决定：多栏时要把 doneAt / 排队清空 / 水位写回
    // 推到最后一栏完成；单栏时立即执行（与原来等价）。
    const stillStreaming = get().messages.some((m) => m.role === 'assistant' && m.streaming)
    if (stillStreaming) {
      // 还有栏没跑完：水位是「本轮最后状态」，留到收尾时再写
      return
    }
    set((s) => ({
      turnStats: { ...s.turnStats, doneAt: Date.now() },
      queuedSteers: [],
      // done 带水位才写：不带（旧后端/未上报）保持原值，别把已知水位冲成 null
      ...(context ? { contextUsage: { used: context.used, total: context.total } } : {}),
    }))
  }

  const onDone: StreamHandlers['onDone'] = (context, origin) => finishLane(context, origin)

  return {
    handlers: { onUsage, onProgress, onStreamEnd, onDegraded, onError, onDone },
    finishAssistant,
  }
}
