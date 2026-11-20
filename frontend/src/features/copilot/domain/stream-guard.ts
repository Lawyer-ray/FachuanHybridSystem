/**
 * 流的两种「不对劲」：**上游安静**（只提示）与**收尾残缺**（标截断）。
 *
 * 两条都是真实事故：
 *
 * 1. **安静 → 无限转圈**：dsh / openai-agents 调一个长工具时后端**一个心跳都不发**，
 *    界面上只有一行「正在查 XX…」在转。律师盯 3 分钟不知道是后端在干活还是连接死了。
 *    → {@link IdleWatchdog} 记两个时钟，超阈值只**提示**。
 * 2. **缺 done → 静默空栏**：三栏只到 1 个 done 时，另两栏既没有正文也没有标记，
 *    看起来像「AI 回答了但内容丢了」。→ {@link classifyStreamEnd} 按栏清单比对
 *    done 集合，缺的栏标 `truncated`（**不是** `failed`：它不是失败，是没等到）。
 *
 * ## 血的教训：idle 只能提示，绝不能 abort
 *
 * 上一版把「上游 90 秒没动静」当成断线并 abort 掉 fetch。结果是**长工具一律被杀**：
 * 工具在服务端跑 2 分钟是完全正常的（读大文件夹、批量检索裁判文书），而这期间
 * 连接上一个字节都没有——abort 之后律师拿到的是半句话，比转圈糟糕得多。
 * 所以本模块**没有任何中止能力**：`IdleWatchdog.check()` 只返回一句文案，
 * 它连 AbortController 都拿不到。真正的中止只有两个触发者——用户按停止、fetch 报错。
 *
 * 全部为纯逻辑（无 React / 无 fetch），fake timers 与注入时钟都能测。
 */

/**
 * 上游安静多久开始提示。
 *
 * 45 秒的来源：实测最慢的几个工具调用（`tool_search` 冷启动、大目录
 * `list_folder_files`）在 16~30 秒之间返回，安静 45 秒意味着「这次明显比平时慢」，
 * 提示有价值；而律师开始怀疑「是不是卡死了」大约在 1 分钟。取两者之间，
 * 既不打断正常慢工具，也不让他干等到自己去刷新页面。
 */
export const IDLE_HINT_MS = 45_000

/** 断流（连接结束但没见到 done）的文案。与 domain/error.ts 的 `连接提前结束` 同源 */
export const DISCONNECTED_NOTICE = '与本轮的连接提前结束，回答可能不完整'

/** 闲置毫秒数 → 「上游安静 N 秒…」文案；未到阈值返回 `null` */
export function idleHintText(idleMs: number, thresholdMs: number = IDLE_HINT_MS): string | null {
  if (idleMs < thresholdMs) return null
  // 向下取整到秒：文案里出现小数只会显得像 bug
  const seconds = Math.floor(idleMs / 1000)
  // 「不会中断」是必须写出来的那半句：不写的话，律师看到「上游安静 120 秒」的第一
  // 反应是「那还不快停」，而我们的契约恰恰是**绝不停**（见文件头注释）
  return `上游安静 ${seconds} 秒…（仍在等待，不会中断）`
}

/**
 * 「有字节、但一直没有新内容」的提示阈值（毫秒）。
 *
 * 定成安静阈值的 3 倍而不是同一个数：心跳只证明连接活着，并不证明模型有进展。
 * 同一个阈值会让每一轮长工具都在 45 秒处同时弹两句不同的话，而它俩说的是同一件事。
 */
export const CONTENT_HINT_MS = IDLE_HINT_MS * 3

export interface IdleWatchdogOptions {
  /** 字节安静多久开始提示（默认 {@link IDLE_HINT_MS}） */
  idleHintMs?: number
  /** 有字节、但多久没有新内容才提示（默认 {@link CONTENT_HINT_MS}） */
  contentHintMs?: number
  /** 时钟注入（测试用；默认 `Date.now`） */
  now?: () => number
}

/**
 * 双计时的安静检测器：`lastByteAt`（收到任意帧）与 `lastContentAt`（收到正文/思考）。
 *
 * 为什么是两个时钟而不是一个：这两种「安静」的含义完全不同——
 * - 字节也没有（`byteIdleMs` 大）：连接/网关层可能断了，说「上游安静 N 秒」；
 * - 有字节但没内容（`contentIdleMs` 大、`byteIdleMs` 小）：后端在跑工具/等审批，
 *   说「上游在响应，但 N 秒没有新内容」。
 *
 * 一个时钟会把这两种混成同一句话，律师据此做的判断也就跟着错（一个是「该重启」，
 * 一个是「再等等」）。
 *
 * **本类没有 abort**：只观察、只出文案。要有中止，只能由调用方在用户操作或
 * fetch 异常时自己做（见文件头「血的教训」）。
 */
export class IdleWatchdog {
  private readonly idleHintMs: number
  private readonly contentHintMs: number
  private readonly clock: () => number
  private lastByteAt: number
  private lastContentAt: number

  constructor(options: IdleWatchdogOptions = {}) {
    this.idleHintMs = options.idleHintMs ?? IDLE_HINT_MS
    this.contentHintMs = options.contentHintMs ?? this.idleHintMs * 3
    this.clock = options.now ?? (() => Date.now())
    const at = this.clock()
    this.lastByteAt = at
    this.lastContentAt = at
  }

  /** 收到任意字节（任何一帧，含 heartbeat / 注释行）——只观察，不判断内容 */
  touchByte(at: number = this.clock()): void {
    this.lastByteAt = at
  }

  /** 收到正文/思考增量。内容也是字节，所以两个时钟一起推 */
  touchContent(at: number = this.clock()): void {
    this.lastByteAt = at
    this.lastContentAt = at
  }

  /** 距上次收到任意字节的毫秒数 */
  byteIdleMs(at: number = this.clock()): number {
    return Math.max(0, at - this.lastByteAt)
  }

  /** 距上次收到正文/思考的毫秒数 */
  contentIdleMs(at: number = this.clock()): number {
    return Math.max(0, at - this.lastContentAt)
  }

  /**
   * 现在该提示什么；`null` = 不该提示（还没到阈值，或刚收到东西）。
   *
   * 两档，按「安静的是字节还是内容」分：
   * - 字节也安静了 → 「上游安静 N 秒…」（可能断了，但**绝不停**）；
   * - 字节在流动、只是没有新内容（心跳/注释行）→ 更晚才说「上游在响应，但 N 秒
   *   没有新内容…」，避开「每轮长工具都报一次警」的噪音。
   *
   * **恢复收到帧即清除**：`touchByte` 之后字节不太可能已经又安静满一个阈值，所以
   * `check()` 自然回到 `null`——调用方不必自己记「提示过没有」。
   */
  check(at: number = this.clock()): string | null {
    const byteIdle = this.byteIdleMs(at)
    if (byteIdle >= this.idleHintMs) return idleHintText(byteIdle, this.idleHintMs)
    const contentIdle = this.contentIdleMs(at)
    if (contentIdle < this.contentHintMs) return null
    return `上游在响应，但 ${Math.floor(contentIdle / 1000)} 秒没有新内容…`
  }

  /** 重置两个时钟（新一轮开流时用） */
  reset(at: number = this.clock()): void {
    this.lastByteAt = at
    this.lastContentAt = at
  }
}

/** 收尾判定的事实输入（全部来自流消费层，本函数不碰 IO） */
export interface StreamEndFacts {
  /**
   * 本轮**登记的栏**（agent kind，顺序即栏序）。
   *
   * 单栏传 `[]`：那时没有「哪一栏的 done」这个概念，整条流的 done 就是唯一收尾信号
   * （单栏轮次的事件照样带后端的 `agent`，拿它去比对会把「后端默认 pi、本轮没登记
   * 任何 kind」误判成缺 done）。
   */
  lanes: readonly string[]
  /** 收到过 done 的栏（只认帧里**显式**的 `agent`） */
  doneKinds: readonly string[]
  /**
   * 收到过「没写 agent」的会话级 done。
   *
   * 旧后端 / 单后端口径只发一条不带来源的 done，语义是「整轮结束」。这时一律
   * 认为每栏都收尾了——否则升级当期，所有多栏轮次都会被打上「已中断」。
   */
  sessionLevelDone: boolean
}

export interface StreamEndVerdict {
  /** 是否见到过 done（任一栏算） */
  sawDone: boolean
  /** 没等到 done 的栏（单栏时恒为空） */
  missingLanes: string[]
  /** 整轮是否应按截断呈现（缺 done 就是截断，不管此前报没报过错） */
  truncated: boolean
  /** 给律师看的一句话；`null` = 正常收尾，不必多说 */
  notice: string | null
}

/**
 * 流的收尾结论：本轮登记的栏 vs 实际收到 done 的栏。
 *
 * 为什么需要它：`consumeAgentStream` 只回一个全局 `sawDone`，于是「三栏里只到
 * 了一栏的 done」和「全跑完了」在前端看起来一模一样——另两栏既不标截断也没有
 * 错误，就安静地留两个空栏（真实事故，见 `<MessageList>` 的「（无内容）」）。
 *
 * 为什么缺 done 标 `truncated` 而不是 `failed`：那是**没等到**，不是**跑失败**
 * （后端可能还在跑，只是连接断了）。标成「本轮未做」会让律师以为后端拒绝了这一栏，
 * 于是去重发一次；「已中断」才会让他知道「回答可能不完整」。
 *
 * `notice` 只在**没有更具体的错误**时才该显示（调用方用 `lastError ?? notice`）：
 * 后端已经说了「对比执行位已满」，再叠一句「连接提前结束」只会把人绕晕。
 */
export function classifyStreamEnd(facts: StreamEndFacts): StreamEndVerdict {
  const done = new Set(facts.doneKinds)
  const sawDone = facts.sessionLevelDone || done.size > 0

  if (facts.lanes.length === 0) {
    return {
      sawDone,
      missingLanes: [],
      truncated: !sawDone,
      notice: sawDone ? null : DISCONNECTED_NOTICE,
    }
  }

  const missingLanes = facts.sessionLevelDone ? [] : facts.lanes.filter((kind) => !done.has(kind))
  if (!sawDone) {
    // 一栏 done 都没有：这就是断流，措辞要说清「连接」，而不是「等某几栏」
    return { sawDone, missingLanes, truncated: true, notice: DISCONNECTED_NOTICE }
  }
  if (missingLanes.length > 0) {
    return {
      sawDone,
      missingLanes,
      truncated: true,
      notice: `未等到 ${missingLanes.join(' / ')} 的完成信号，这几栏的回答可能不完整`,
    }
  }
  return { sawDone, missingLanes: [], truncated: false, notice: null }
}
