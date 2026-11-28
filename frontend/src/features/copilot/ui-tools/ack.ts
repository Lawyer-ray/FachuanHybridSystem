/**
 * 界面动作的**真实结果回执**：把「页面到底变成了什么样」送回后端那一跳的等待方。
 *
 * ## 为什么这一跳在前端
 *
 * pi 后端的会话由子进程持有，Django 没法在两跳之间往会话里插系统消息——**工具返回值
 * 是唯一的注入点**。模型调完界面动作能看见什么，取决于这里发没发、发得多快：不发，
 * 后端只能等到超时，模型永远拿到 `observed: false`，「已经帮你切好了」就只能靠猜。
 *
 * ## 为什么尽力而为（不 await、只重试一次、永不 reject）
 *
 * 回执是**旁路证据**：它发出之前页面动作早就真的落完了。让回执的失败变成律师侧的
 * 失败（或让下一次点击等它）是本末倒置——所以最多重试一次，最终失败只留一句 warn。
 *
 * ## 为什么 observed_location 读调用这一刻的 window
 *
 * 「真的变了」只有执行**之后**的地址能证明：执行器可能被 replace、可能被路由改写、
 * 也可能压根没跳。回填模型请求的那个地址等于自证，读动作前的快照同样等于自证。
 *
 * 为什么不进 `ui-tools/index.ts` 桶：那个桶承诺「零运行时依赖、node 单测可直接加载」，
 * 而本文件要 POST（会把 `../api` → ky 拖进依赖链），故由 `store/ui-tools.ts` 深引。
 */

import { submitUiActionResult } from '../api'
import type { UiActionResultAck, UiActionResultSettlement } from './types'

/** 重试间隔：够盖住一次瞬时抖动，又不至于让回执晚到毫无意义（后端只等 ack ≤2s） */
const RETRY_DELAY_MS = 300
/** detail 上限（契约 ≤200 字）：截断而不是丢弃，前 200 字通常已够判断成败 */
const DETAIL_MAX = 200

/** 注入点（默认真实 window）：node 单测没有 window，也便于断言「取的是当次的值」 */
export interface AckPorts {
  currentLocation?: () => string
}

/** 执行之后的真实地址，与执行器端口的 `currentPath` 同口径（pathname + search） */
function browserLocation(): string {
  if (typeof window === 'undefined') return ''
  return window.location.pathname + window.location.search
}

/**
 * 截到 `DETAIL_MAX` 个字。
 *
 * 按**码点**截而不是 `slice`：切在半个代理对上会让 JSON 里出现孤立代理项，
 * 后端一存一读就成了非法字符。
 */
function clipDetail(detail: string | undefined): string | undefined {
  if (detail === undefined) return undefined
  const chars = Array.from(detail)
  return chars.length <= DETAIL_MAX ? detail : chars.slice(0, DETAIL_MAX).join('')
}

/** 失败原因压成一句：warn 里要说清是哪一类，又不该把整个 Error 对象打出来 */
function reasonOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error)
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/**
 * 发一次结算回执。**永不 reject**，调用方一律不 await（见文件头）。
 */
export async function ackUiActionResult(
  settlement: UiActionResultSettlement,
  ports: AckPorts = {},
): Promise<void> {
  const payload: UiActionResultAck = {
    ...settlement,
    detail: clipDetail(settlement.detail),
    observed_location: ports.currentLocation?.() ?? browserLocation(),
  }
  let failure: unknown = null
  // 立刻一次 + 300ms 后一次：两次都失败说明后端那一跳已经不在了，再试只是拖时间
  for (const delay of [0, RETRY_DELAY_MS]) {
    if (delay > 0) await sleep(delay)
    try {
      await submitUiActionResult(payload)
      return
    } catch (error) {
      failure = error
    }
  }
  console.warn(`[ui-action] 结果回执未送达（call_id=${payload.call_id}）：${reasonOf(failure)}`)
}
