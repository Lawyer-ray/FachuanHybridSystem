/**
 * store slice：界面动作（`ui_action`）的执行态 —— 幂等 / 打断 / 失败落态 / 结算回执 / 批次排队。
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
 * ## 为什么去重表与批次闸门在模块级而不是 state
 *
 * `seenCallIds` 与「非幂等动作的同参 5 秒窗」只服务执行期守卫，没有组件要订阅它们；
 * 放进 `CopilotState` 的代价是每次动作都触发一遍全局订阅者比较。批次闸门同理（没有组件
 * 关心「哪一批在排队」）。打断标记 `abortedAt` 相反——横幅要据它决定还挂不挂「停下」，
 * 所以它在 state 里。
 *
 * ## 为什么失败必须 toast
 *
 * 结算会一并回执给后端（见 `ack`），但那条路是给**模型**看的、且尽力而为：它可能
 * 两次都没发出去，也可能要等模型下一次 poll 才被读到。律师此刻看得见的只有页面，
 * 静默失败的后果是 AI 在对话里说「已经帮你打开了」，而页面一动不动、也没有任何解释。
 *
 * ## 批次（`ui_action_batch`）为什么在这里排队
 *
 * 一次确认可以带 2~5 步，帧是连着到的，而每一步都要落运行记录、发回执。同批的语义
 * **有先后**（先跳页再切 stage ≠ 先切 stage 再跳页），并发执行会让审批卡上那句「将按
 * 顺序执行」变成假承诺。所以同 `batchId` 的后一条要等前一条**结算**（不是「已发起」）。
 * 不同批次互不阻塞——两个批次本来就是两件互不相干的事。
 *
 * 失败即中止：同批任一步失败、或律师按下「停下」，**后续步骤一律标 aborted 并回执**，
 * 不做「跳过它继续跑剩下的」——律师看到的是「一半动了」，而模型没法判断页面停在哪。
 *
 * 并发：单步动作仍不做互斥（毫秒级、last-writer-wins）；`confirm` / `guarded` 真正接入
 * 时必须在这里加「同一时刻只允许一个写动作在飞」的互斥（08 §4.2）。
 */

import { UI_TOOL_SPECS, runUiTool, validateArgs } from '../ui-tools'
// 深引而不是走桶：`ui-tools/index.ts` 承诺零运行时依赖（回执要发 POST，会把 ky 拖进来）
import { ackUiActionResult } from '../ui-tools/ack'
import type {
  UiActionRequest,
  UiActionResultSettlement,
  UiToolErrorCode,
  UiToolOutcome,
  UiToolPorts,
} from '../ui-tools'
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
/** 同一批最多几步（与后端 `MAX_BATCH_STEPS` 对齐）：等待队列的上限，超限说明契约已漂移 */
const BATCH_LIMIT = 5

/** 已受理过的 callId（LRU：Set 保持插入序，超限时删最旧的） */
const seenCallIds = new Set<string>()
/** 非幂等动作最近一次执行时刻（键 = 动作名 + 稳定序列化参数） */
const recentNonIdempotent = new Map<string, number>()

/**
 * 一条批次闸门（键 = `batchId`）。
 *
 * `tail` 是「前一条的结算时刻」：后一条 await 它就实现了同批串行。`stopped` 一旦置位，
 * 同批后续步骤一律 aborted——失败即中止，不做「跳过继续」。
 */
interface BatchGate {
  /** 已受理的步骤数（判等待队列上限） */
  accepted: number
  /** 同批已有步骤失败 / 被停下 → 后续步骤不再执行 */
  stopped: boolean
  /** 前一条的结算时刻 */
  tail: Promise<void>
}
/** 打开的批次。最后一条结算时删掉，否则长会话按批次数无限长大 */
const batchGates = new Map<string, BatchGate>()

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

/** 本条所属批次的闸门；单步动作（没有批次）返回 null —— 不排队，立即执行 */
function gateOf(batchId: string | null | undefined): BatchGate | null {
  if (typeof batchId !== 'string' || batchId === '') return null
  const existing = batchGates.get(batchId)
  if (existing) return existing
  const gate: BatchGate = { accepted: 0, stopped: false, tail: Promise.resolve() }
  batchGates.set(batchId, gate)
  return gate
}

/** 运行记录的公共字段：动作名、开始时刻、批次身份（单步动作的批次是 null / 0） */
function runMeta(
  req: UiActionRequest,
  startedAt: number,
): Pick<UiToolRun, 'name' | 'startedAt' | 'batchId' | 'batchIndex'> {
  return { name: req.action, startedAt, batchId: req.batchId ?? null, batchIndex: req.batchIndex ?? 0 }
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

  /**
   * 结算回执：把真实结果送回后端那一跳（工具返回值是模型唯一的注入点）。
   *
   * 一律 `void`：回执是旁路证据，动作早在毫秒内落完了，等它只会让律师的点击看起来
   * 卡住；`ackUiActionResult` 自身永不 reject（见 ui-tools/ack.ts）。
   */
  const ackResult = (req: UiActionRequest, settlement: Omit<UiActionResultSettlement, 'call_id'>): void => {
    void ackUiActionResult({ call_id: req.callId, ...settlement })
  }

  /** 标 aborted 并回执：软打断与「同批已中止」共用一条路径（不发回执，后端只能等到超时） */
  const markAborted = (req: UiActionRequest, detail?: string): void => {
    const now = Date.now()
    writeRun(req.callId, { ...runMeta(req, now), state: 'aborted', code: 'aborted', endedAt: now })
    ackResult(req, detail === undefined ? { outcome: 'aborted' } : { outcome: 'aborted', detail })
  }

  /** 执行一条动作：幂等 / 打断 / 失败落态 / 回执。批次排队在外层 `runUiAction`（见文件头） */
  const runOne = async (req: UiActionRequest): Promise<void> => {
    const startedAt = Date.now()
    const base = runMeta(req, startedAt)
    const ack = (settlement: Omit<UiActionResultSettlement, 'call_id'>): void => ackResult(req, settlement)
    /** 落失败态并让律师看见（静默失败 = 「AI 说帮你开，页面一动不动」） */
    const fail = (code: UiToolErrorCode, message: string): void => {
      writeRun(req.callId, { ...base, state: 'error', code, endedAt: Date.now() })
      hostPorts?.toast(message)
      ack({ outcome: 'error', code, detail: message })
    }

    // 「停下」之后的动作一律不执行：软打断只挡**后续**动作（08 §4.5），已发出的不追回
    // ——它们在毫秒内就落完了。
    if (get().abortedAt !== null) {
      markAborted(req)
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
      ack({ outcome: 'error', code: 'executor_error', detail: '界面动作宿主（面板 / 助手页）未挂载' })
      return
    }
    // 非幂等动作的同参重试按 5 秒窗挡掉（08 §6）。命中就静默丢：它本来就是「同一次
    // 操作被重发」，再弹一次错误提示反而制造噪音。
    // 也不回执：这一次**什么都没执行**，回 ok 是撒谎，而契约里没有「已去重」这个码。
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
      ack({ outcome: 'ok', detail: outcome.detail })
      return
    }
    fail(outcome.code, outcome.message)
  }

  return {
    uiToolRuns: {},
    abortedAt: null,

    runUiAction: async (req: UiActionRequest) => {
      // 同一 callId 只执行一次：模型重试与事件重放都会再来一遍。重复导航只是白跳一下，
      // 重复执行一次写库动作就是事故，所以从第一档起就按最严的口径挡。
      // 重复投递不回执：第一次投递已经发过，再发一遍只会让后端的 pending 表多一条假结算。
      // 也在排队之前挡：重放的帧不该占掉一个队位。
      if (rememberCallId(req.callId)) return

      const batchId = req.batchId
      const gate = gateOf(batchId)
      if (!gate) {
        await runOne(req)
        return
      }
      if (gate.accepted >= BATCH_LIMIT) {
        // 契约外（后端一批最多 5 步）：既不无限排队，也不悄悄丢——留失败记录 + 回执
        const now = Date.now()
        writeRun(req.callId, { ...runMeta(req, now), state: 'error', code: 'executor_error', endedAt: now })
        ackResult(req, {
          outcome: 'error',
          code: 'executor_error',
          detail: `同一批最多 ${BATCH_LIMIT} 步，这一步没有执行`,
        })
        gate.stopped = true
        return
      }
      gate.accepted += 1

      // 排队：自己的结算 Promise 接到队尾，后一条就等它（同批串行，见文件头）
      const previous = gate.tail
      let release: () => void = () => {}
      const own = new Promise<void>((resolve) => {
        release = resolve
      })
      gate.tail = own
      try {
        await previous
        if (gate.stopped) {
          markAborted(req, '同批已有步骤失败或被停下，这一步没有执行')
          return
        }
        await runOne(req)
      } finally {
        // 判据看运行记录而不是返回值：runOne 有多条 return，改一处就会漏一处。
        // 只有 `ok` 才算通过；没有记录 = 什么都没执行（同参去重），不算失败。
        const run = get().uiToolRuns[req.callId]
        if (run && run.state !== 'ok') gate.stopped = true
        release()
        // 最后一条结算完就把闸门删掉（没人再等它），否则长会话按批次数无限长大
        if (batchId && gate.tail === own) batchGates.delete(batchId)
      }
    },

    abortUiActions: () => {
      // 幂等：连点「停下」只记第一次的时刻，之后到达的动作都按那一刻起算
      if (get().abortedAt !== null) return
      set({ abortedAt: Date.now() })
    },
  }
}
