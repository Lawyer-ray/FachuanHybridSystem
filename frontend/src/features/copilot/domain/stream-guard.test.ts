/**
 * 流的「安静提示」与「收尾判定」。
 *
 * 这两条判据错了都不会抛异常，只会让界面**安静地骗人**：
 * - 安静提示的阈值判错 → 要么永远不出现（律师干等 3 分钟去刷新页面），
 *   要么一开流就出现（每轮都报警，很快就被无视）；
 * - 收尾判定把「缺 done」当成「跑完了」→ 三栏里两栏空白且无任何标记，
 *   看起来像「AI 回答了但内容丢了」（真实事故）。
 *
 * 还有一条**回归红线**：idle 只能提示，绝不能 abort。上一版拿 90 秒无字节去
 * abort fetch，把服务端正常跑着的长工具一律杀在半路。所以这里直接断言
 * IdleWatchdog **没有**任何中止能力——谁再往上加 abort，这条测试先红。
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  classifyStreamEnd,
  DISCONNECTED_NOTICE,
  IDLE_HINT_MS,
  IdleWatchdog,
  idleHintText,
} from './stream-guard'

describe('idleHintText（文案口径）', () => {
  it('不到阈值不提示', () => {
    expect(idleHintText(0)).toBeNull()
    expect(idleHintText(IDLE_HINT_MS - 1)).toBeNull()
  })

  it('到阈值给出秒数 + 「不会中断」', () => {
    // 「不会中断」这四个字是必须写出来的：只说「安静 120 秒」，律师的第一反应是
    // 「那还不快停」，而我们的契约恰恰是绝不停（见 stream-guard 文件头）
    expect(idleHintText(IDLE_HINT_MS)).toBe('上游安静 45 秒…（仍在等待，不会中断）')
    expect(idleHintText(120_400)).toBe('上游安静 120 秒…（仍在等待，不会中断）')
  })
})

describe('IdleWatchdog（双计时；只提示，绝不 abort）', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(0)
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('刚开流不提示；安静超过阈值才提示', () => {
    const watchdog = new IdleWatchdog()
    expect(watchdog.check()).toBeNull()

    vi.advanceTimersByTime(IDLE_HINT_MS - 1_000)
    expect(watchdog.check()).toBeNull()

    vi.advanceTimersByTime(6_000)
    expect(watchdog.check()).toBe('上游安静 50 秒…（仍在等待，不会中断）')
  })

  it('恢复收到帧即清除提示（调用方不必自己清）', () => {
    const watchdog = new IdleWatchdog()
    vi.advanceTimersByTime(60_000)
    expect(watchdog.check()).not.toBeNull()

    watchdog.touchByte()
    expect(watchdog.check()).toBeNull()
    expect(watchdog.byteIdleMs()).toBe(0)
  })

  it('有心跳但没正文：文案换成「在响应，但没有新内容」', () => {
    // 后端在跑工具时可能只发心跳/注释行：这时说「上游安静」是错的判断，
    // 律师会去查网络，而实际上后端活得好好的
    const watchdog = new IdleWatchdog()
    // 心跳每 10 秒一次：字节一直新鲜，但正文一直没来
    for (let i = 0; i < 15; i += 1) {
      vi.advanceTimersByTime(10_000)
      watchdog.touchByte()
    }
    expect(watchdog.contentIdleMs()).toBe(150_000)
    expect(watchdog.byteIdleMs()).toBe(0)
    // 40 秒处就该安静了，但有心跳时说的是另一句话（且出现得更晚）
    expect(watchdog.check()).toBe('上游在响应，但 150 秒没有新内容…')
  })

  it('正文本身也是字节：touchContent 同时推两个时钟', () => {
    const watchdog = new IdleWatchdog()
    vi.advanceTimersByTime(60_000)
    watchdog.touchContent()
    expect(watchdog.byteIdleMs()).toBe(0)
    expect(watchdog.contentIdleMs()).toBe(0)
    expect(watchdog.check()).toBeNull()
  })

  it('时间回拨不产生负闲置（Math.max 兜底）', () => {
    const watchdog = new IdleWatchdog({ now: () => 1_000 })
    expect(watchdog.byteIdleMs(500)).toBe(0)
  })

  it('红线：没有任何中止能力（idle 只提示，abort 只由用户/网络异常触发）', () => {
    const watchdog = new IdleWatchdog()
    expect(Object.keys(watchdog)).not.toContain('abort')
    expect((watchdog as unknown as { abort?: unknown }).abort).toBeUndefined()
    expect((watchdog as unknown as { controller?: unknown }).controller).toBeUndefined()
    // 安静再久也只返回文案，不会抛、不会改外部状态
    vi.advanceTimersByTime(10 * 60_000)
    expect(typeof watchdog.check()).toBe('string')
  })

  it('reset 把两个时钟归零（新一轮开流复用同一个实例时）', () => {
    const watchdog = new IdleWatchdog()
    vi.advanceTimersByTime(60_000)
    watchdog.reset()
    expect(watchdog.check()).toBeNull()
  })

  it('阈值可注入（测试与「更晚才提示」的调用方都需要）', () => {
    const watchdog = new IdleWatchdog({ idleHintMs: 5_000 })
    vi.advanceTimersByTime(6_000)
    expect(watchdog.check()).toBe('上游安静 6 秒…（仍在等待，不会中断）')
  })
})

describe('classifyStreamEnd（收尾是否残缺）', () => {
  it('单栏收到 done：正常收尾，不多说一句', () => {
    const verdict = classifyStreamEnd({ lanes: [], doneKinds: ['pi'], sessionLevelDone: false })
    expect(verdict).toEqual({ sawDone: true, missingLanes: [], truncated: false, notice: null })
  })

  it('单栏在 EOF 处没有 done：断流，必须标截断并给文案', () => {
    const verdict = classifyStreamEnd({ lanes: [], doneKinds: [], sessionLevelDone: false })
    expect(verdict.sawDone).toBe(false)
    expect(verdict.truncated).toBe(true)
    expect(verdict.notice).toBe(DISCONNECTED_NOTICE)
    // 文案要能被 domain/error.ts 的分类接住（「连接提前结束」是它的 match key）
    expect(verdict.notice).toContain('连接提前结束')
  })

  it('三栏只到一栏 done：全局 sawDone 为真，但另两栏必须缺出来（就是那个静默空栏 bug）', () => {
    const verdict = classifyStreamEnd({
      lanes: ['pi', 'dsh', 'oai'],
      doneKinds: ['pi'],
      sessionLevelDone: false,
    })
    // 关键：sawDone 是 true——只看它就以为这轮跑完了
    expect(verdict.sawDone).toBe(true)
    expect(verdict.missingLanes).toEqual(['dsh', 'oai'])
    expect(verdict.truncated).toBe(true)
    expect(verdict.notice).toContain('dsh / oai')
    expect(verdict.notice).toContain('不完整')
  })

  it('缺 done 的栏顺序跟栏序一致（栏头左右顺序不能被 Set 打乱）', () => {
    const verdict = classifyStreamEnd({
      lanes: ['oai', 'pi', 'dsh'],
      doneKinds: ['pi'],
      sessionLevelDone: false,
    })
    expect(verdict.missingLanes).toEqual(['oai', 'dsh'])
  })

  it('三栏都收到 done：不标截断', () => {
    const verdict = classifyStreamEnd({
      lanes: ['pi', 'dsh', 'oai'],
      doneKinds: ['pi', 'dsh', 'oai'],
      sessionLevelDone: false,
    })
    expect(verdict).toEqual({ sawDone: true, missingLanes: [], truncated: false, notice: null })
  })

  it('旧后端只发一条不带来源的 done：按会话级收尾，不许把三栏全标中断', () => {
    // 升级当期最怕的就是这个：老口径的 done 没有 agent，若按「没匹配到栏」处理，
    // 每一轮正常对话都会被打上「已中断」
    const verdict = classifyStreamEnd({ lanes: ['pi', 'dsh'], doneKinds: [], sessionLevelDone: true })
    expect(verdict).toEqual({ sawDone: true, missingLanes: [], truncated: false, notice: null })
  })

  it('一栏 done 都没有、也没会话级 done：整轮截断（多栏也归「连接提前结束」）', () => {
    const verdict = classifyStreamEnd({ lanes: ['pi', 'dsh'], doneKinds: [], sessionLevelDone: false })
    expect(verdict.sawDone).toBe(false)
    expect(verdict.truncated).toBe(true)
    expect(verdict.notice).toBe(DISCONNECTED_NOTICE)
  })
})
