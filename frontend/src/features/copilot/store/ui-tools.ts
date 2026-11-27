/**
 * store slice：界面动作（`ui_action`）的执行态 —— 幂等 / 打断 / 失败落态。
 *
 * ## 为什么 ui 动作不进转录消息
 *
 * 一条动作的结果**已经落在页面上**（页面真的跳了、面板真的开了），往转录里再写一行
 * 「已跳转到 /material-prep?stage=todo」是同一件事说两遍；更糟的是它**回放不出来**
 * ——重新加载历史时读到那行字，页面并不会跟着跳一次，律师拿到的是一句没有效果的空话。
 * 转录记「谁说了什么」，界面动作记「谁点了什么」，两者生命周期不同，所以运行态只留在
 * 这里，由 `UiActionBanner` 读出来显示「AI 正在操作」，转录一个字都不写
 * （08 §9 / 04 §8 的刻意取舍）。
 *
 * ## 为什么去重表在模块级而不是 state
 *
 * `seenCallIds` 与「非幂等动作的同参 5 秒窗」只服务执行期守卫，没有组件要订阅它们；
 * 放进 `CopilotState` 的代价是每次动作都触发一遍全局订阅者比较。打断标记 `abortedAt`
 * 相反——横幅要据它决定还挂不挂「停下」，所以它在 state 里。
 *
 * ## 为什么失败必须 toast
 *
 * 执行结果不回传模型（T1 单向指令，08 §3.1）：失败现场只剩前端。静默失败的后果是
 * AI 在对话里说「已经帮你打开了」，而页面一动不动、也没有任何解释。
 *
 * 并发：本次只有 `safe` 动作（毫秒级、last-writer-wins），不做串行队列；`confirm` /
 * `guarded` 真正接入时必须在这里加「同一时刻只允许一个写动作在飞」的互斥（08 §4.2）。
 */

import { UI_TOOL_SPECS, runUiTool, validateArgs } from '../ui-tools'
import type { UiActionRequest, UiToolErrorCode, UiToolOutcome, UiToolPorts } from '../ui-tools'
import type { UiToolRun } from '../state-types'
import type { CopilotState } from '../types'
import type { Slice } from './slice'

/** 清单项类型从清单自己推导：动作字段与生成物永远一致，不另抄一份 */
type UiToolSpec = (typeof UI_TOOL_SPECS)[number]

/** 幂等键 LRU 上限（08 §6）：够覆盖一轮长对话的重放，又不会无界增长 */
const SEEN_CALLID_LIMIT = 200
/** 非幂等动作的同参去重窗口（08 §6）：模型重试与「律师真想再点一次」只能靠时间区分 */
const NON_IDEMPOTENT_WINDOW_MS = 5_000
/** 运行记录的保留条数：横幅只读最近一条，长会话里没必要越攒越多 */
const RUN_LOG_LIMIT = 50

/** 已受理过的 callId（LRU：Set 保持插入序，超限时删最旧的） */
const seenCallIds = new Set<string>()
/** 非幂等动作最近一次执行时刻（键 = 动作名 + 稳定序列化参数） */
const recentNonIdempotent = new Map<string, number>()

/** 宿主端口；null = 面板与助手页都没挂载 */
let hostPorts: UiToolPorts | null = null

/**
 * 注入/撤销宿主端口。
 *
 * React 之外拿不到 router（main.tsx 是声明式 `<BrowserRouter>`，08 §4.1），所以导航
 * 只能在组件里用 `useNavigate()` 捕获后注入；组件卸载时传 null，避免调到已卸载路由器的
 * navigate 上。
 */
export function setUiToolPorts(next: UiToolPorts | null): void {
  hostPorts = next
}

/**
 * 按「归属」撤销端口：当前槽位还是我这一份才置空。
 *
 * 为什么不能直接 `setUiToolPorts(null)`：宿主有两个（`CopilotPanel` 与
 * `AssistantPage`，08 §4.1 已说明为什么要两处），而槽位只有一个。无条件置空的话，
 * 「关一下面板」会把助手页刚注入的端口一起干掉，表现为“面板关过之后 AI 再也操作不了
 * 页面”，而且只落一条 `executor_error`，极难归因（评审 P2-6）。
 * 另：`main.tsx` 开了 StrictMode，挂载/卸载会双跑，归属校验比计数更不容易写错。
 */
export function releaseUiToolPorts(owned: UiToolPorts): void {
  if (hostPorts === owned) hostPorts = null
}

/** 动作名 → 清单项。清单是闭集，但动作名来自网络，未知名字必须落到 undefined */
function specOf(action: string): UiToolSpec | undefined {
  return UI_TOOL_SPECS.find((spec) => spec.name === action)
}

/** 稳定序列化：键排序后再序列化，参数书写顺序不同不该算成两个不同的动作 */
function stableKey(action: string, args: Record<string, unknown>): string {
  const pairs = Object.keys(args)
    .sort()
    .map((key) => [key, args[key]] as const)
  return `${action}:${JSON.stringify(pairs)}`
}

/** 记一次 callId；返回 true = 之前已见过（重复投递 / 事件重放） */
function rememberCallId(callId: string): boolean {
  if (seenCallIds.has(callId)) return true
  seenCallIds.add(callId)
  if (seenCallIds.size > SEEN_CALLID_LIMIT) {
    const oldest = seenCallIds.values().next().value
    if (oldest !== undefined) seenCallIds.delete(oldest)
  }
  return false
}

/** 非幂等动作的同参去重：true = 允许执行（顺带清掉过窗的旧记录，Map 才不胀） */
function allowNonIdempotent(action: string, args: Record<string, unknown>, now: number): boolean {
  for (const [key, at] of recentNonIdempotent) {
    if (now - at > NON_IDEMPOTENT_WINDOW_MS) recentNonIdempotent.delete(key)
  }
  const key = stableKey(action, args)
  const last = recentNonIdempotent.get(key)
  if (last !== undefined && now - last <= NON_IDEMPOTENT_WINDOW_MS) return false
  recentNonIdempotent.set(key, now)
  return true
}

export type UiToolSlice = Pick<CopilotState, 'uiToolRuns' | 'abortedAt' | 'runUiAction' | 'abortUiActions'>

export const createUiToolSlice: Slice<UiToolSlice> = (set, get) => {
  /** 写一条运行记录（同 callId 原地更新；超限时丢最旧的几条） */
  const writeRun = (callId: string, run: UiToolRun): void => {
    set((s) => {
      const next: Record<string, UiToolRun> = { ...s.uiToolRuns, [callId]: run }
      const ids = Object.keys(next)
      if (ids.length > RUN_LOG_LIMIT) {
        ids.sort((a, b) => (next[a]?.startedAt ?? 0) - (next[b]?.startedAt ?? 0))
        for (const stale of ids.slice(0, ids.length - RUN_LOG_LIMIT)) delete next[stale]
      }
      return { uiToolRuns: next }
    })
  }

  return {
    uiToolRuns: {},
    abortedAt: null,

    runUiAction: async (req: UiActionRequest) => {
      // 同一 callId 只执行一次：模型重试与事件重放都会再来一遍。重复导航只是白跳一下，
      // 重复执行一次写库动作就是事故，所以从第一档起就按最严的口径挡。
      if (rememberCallId(req.callId)) return

      const startedAt = Date.now()
      const base = { name: req.action, startedAt }
      /** 落失败态并让律师看见（静默失败 = 「AI 说帮你开，页面一动不动」） */
      const fail = (code: UiToolErrorCode, message: string): void => {
        writeRun(req.callId, { ...base, state: 'error', code, endedAt: Date.now() })
        hostPorts?.toast(message)
      }

      // 「停下」之后的动作一律不执行：软打断只挡**后续**动作（08 §4.5），已发出的不追回
      // ——它们在毫秒内就落完了。
      if (get().abortedAt !== null) {
        writeRun(req.callId, { ...base, state: 'aborted', code: 'aborted', endedAt: startedAt })
        return
      }

      const spec = specOf(req.action)
      if (!spec) {
        // 版本漂移（后端清单比前端新）：不猜测执行，也不假装成功（08 §10）
        fail('unknown_action', `未知的界面动作：${req.action}`)
        return
      }
      if (!validateArgs(spec, req.args)) {
        fail('invalid_args', `「${spec.title}」的参数不合法，已拦下`)
        return
      }
      const ports = hostPorts
      if (!ports) {
        // 面板与助手页都没挂载：连 toast 都发不出去（提示本身就是端口），只留运行记录
        writeRun(req.callId, { ...base, state: 'error', code: 'executor_error', endedAt: startedAt })
        return
      }
      // 非幂等动作的同参重试按 5 秒窗挡掉（08 §6）。命中就静默丢：它本来就是「同一次
      // 操作被重发」，再弹一次错误提示反而制造噪音。
      if (!spec.idempotent && !allowNonIdempotent(req.action, req.args, startedAt)) return

      // 不写 pending：从受理到调用执行器之间没有任何 await，pending 在真实链路里不可观察，
      // 写它只是自欺（懒 chunk / T3 快照那种「已受理未落地」的态接入时再补）。
      writeRun(req.callId, { ...base, state: 'running' })
      // 执行与异常分类都在执行层（ui-tools/registry.runUiTool）：哪个错误码能重试、哪
      // 个要告警是执行层知识，这里只负责「幂等 / 打断 / 落态」。上面先做一遍参数守卫
      // 是为了让非法参数不白占非幂等动作的 5 秒窗。
      // 外再包一层 catch：调用方是 handler 的 `void runUiAction(...)`（不 await），任何
      // 漏出的异常都会变成一条无人处理的 rejection，而不是看得见的失败。
      let outcome: UiToolOutcome
      try {
        outcome = await runUiTool(req, ports)
      } catch (err) {
        fail('executor_error', `界面动作执行失败：${err instanceof Error ? err.message : String(err)}`)
        return
      }
      if (outcome.ok) {
        writeRun(req.callId, { ...base, state: 'ok', endedAt: Date.now() })
        return
      }
      fail(outcome.code, outcome.message)
    },

    abortUiActions: () => {
      // 幂等：连点「停下」只记第一次的时刻，之后到达的动作都按那一刻起算
      if (get().abortedAt !== null) return
      set({ abortedAt: Date.now() })
    },
  }
}
