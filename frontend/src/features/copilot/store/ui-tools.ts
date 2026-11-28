/**
 * store slice：界面动作（`ui_action`）的执行态 —— 幂等 / 打断 / 失败落态 / 结算回执 /
 * 批次排队 / 写动作互斥。
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
 * ## 模块级状态在哪（`./ui-dedupe.ts` 与 `./ui-batch-gate.ts`）
 *
 * 去重表与批次闸门只服务执行期守卫，没有组件要订阅它们；为什么不做成 state、为什么按
 * callId 幂等、为什么有 5 秒同参窗、为什么同批要串行 —— 详细论证跟着代码搬到了这两个
 * 模块的文件头。打断标记 `abortedAt` 相反——横幅要据它决定还挂不挂「停下」，所以它在
 * state 里。
 *
 * ## 为什么失败必须 toast
 *
 * 结算会一并回执给后端（见 `ack`），但那条路是给**模型**看的、且尽力而为：它可能
 * 两次都没发出去，也可能要等模型下一次 poll 才被读到。律师此刻看得见的只有页面，
 * 静默失败的后果是 AI 在对话里说「已经帮你打开了」，而页面一动不动、也没有任何解释。
 *
 * ## 批次（`ui_action_batch`）的排队与「失败即中止」见 `./ui-batch-gate.ts` 文件头
 *
 * 一句话结论：同批后一条等前一条**结算**才跑（审批卡那句「将按顺序执行」才不是假话），
 * 任一步失败或被打断则后续一律 aborted（不做「跳过继续」）。
 *
 * ## 为什么写动作必须互斥（`writeTail` —— 不是体验问题，是丢数据）
 *
 * `confirm` / `guarded` 的执行器最终是 **read-modify-write**：`ui_material_prep_judge`
 * 走 `setPackStatusRemote` —— 先 `getPackDetail(id)` 取回整份 `draft_state`，再整体
 * `saveDraft(id, {…draft, status})` 回写。两个写动作并发在飞时，后写的把先写的结果
 * 整体覆盖（丢更新），而两条回执都报 `ok`：律师看到「都成功了」，库里只剩一半。
 * JS 单线程挡不住这件事——丢掉的不是同步段的交错，而是两个 `await` 之间那段窗口。
 * 所以同一时刻只允许一个 `risk !== 'safe'` 的动作在飞（08 §4.2 原文要求）。
 * 这也是自建项：LangGraph / Temporal 的串行都是「一个 thread / Workflow 内天然如此」，
 * 「多个标签页连同一个会话」两边都没有现成答案。
 *
 * `safe` 动作（跳页 / 开面板 / 切筛选）**不进**这把锁：它们毫秒级、高频，只改 URL 或
 * 视图筛选，压根没有 read-modify-write；串起来只会让律师觉得「点了没反应」。
 *
 * 排队上限 `MAX_WRITE_QUEUE`：在飞的 1 个之外只再收 3 个。超限不是「再等等」，而是
 * 模型在乱发写动作（或帧被重放）；既不执行也不悄悄丢——落失败记录 + 回执，否则后端
 * 只能等到超时。
 *
 * ## 多标签页（见 `./ui-action-claim.ts` 文件头）
 *
 * 两个标签页都会收到同一条帧，`./ui-dedupe.ts` 的 `seenCallIds` 各一份挡不住对方——先抢占的那个执行，
 * 抢不到就静默返回（不落运行记录、不回执）；为什么必须抢占与 TTL 为什么 15 秒见该模块。
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
import { claimUiActionExecution } from './ui-action-claim'
import { runThroughBatchGate } from './ui-batch-gate'
import { allowNonIdempotent, rememberCallId } from './ui-dedupe'
import { confirmGuardedAction } from './ui-guarded-confirm'

/** 清单项类型从清单自己推导：动作字段与生成物永远一致，不另抄一份 */
type UiToolSpec = (typeof UI_TOOL_SPECS)[number]

/** 运行记录的保留条数：横幅只读最近一条，长会话里没必要越攒越多 */
const RUN_LOG_LIMIT = 50
/** 写动作的排队上限（在飞的 1 个之外还能有几个在等）：超限说明模型在乱发写动作 */
const MAX_WRITE_QUEUE = 3
/** 排队超限的回执文案：一句话说清「这一步没执行」，模型才知道不该原样重发 */
const WRITE_QUEUE_FULL_DETAIL = '写动作太多，排队超限，这一步没有执行'

/**
 * 写动作互斥的队尾：`writeTail` 是「最后一个取了写锁的动作的结算时刻」，新的写动作
 * await 它就实现了「同一时刻只有一个写动作在飞」（理由见文件头）。
 *
 * 与 `./ui-batch-gate.ts` 的 `BatchGate.tail` 同一套写法，但管的是两件事：批次闸门管
 * **同一批**的先后（业务顺序，审批卡上的承诺），写锁管**所有写动作**的互斥（丢更新）。
 * 取锁顺序全局一致——**先批次闸门、后写锁**，且写锁的持有者此时不等待任何批次闸门
 * （它只等执行器结账），所以两把锁不会互相死等。改顺序前先把这句话读一遍。
 */
let writeTail: Promise<void> = Promise.resolve()
/** 已取写锁、还没 release 的写动作数（**含在飞的那 1 个**）—— 判排队上限用 */
let writeHolders = 0

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

/**
 * 这条动作要不要占写锁：只有清单里明确写 `safe` 的才放行。
 *
 * 清单外的名字按写动作保守处理（它随后会在 `runOne` 里立刻落 `unknown_action`，多占
 * 一次队位不影响结果）—— 反过来把「不认识的动作」当 safe，等于给版本漂移开一条绕过
 * 互斥的口子。
 */
function isWriteAction(action: string): boolean {
  return specOf(action)?.risk !== 'safe'
}

/**
 * 取写锁：轮到自己时返回 `release`，排队超限返回 `null`（调用方据此落失败 + 回执）。
 *
 * 用「自己的结算 Promise 接到队尾」而不是信号量计数，与 `./ui-batch-gate.ts` 的
 * `BatchGate.tail` 同一路子：先到先得、不必维护「谁是当前持有者」。`release` 必须进
 * finally——少放一次整条队尾就永远卡住，而表现只是「AI 之后的写动作全都没反应」。
 */
async function acquireWriteLock(): Promise<(() => void) | null> {
  // 占用者**含在飞的那 1 个**，所以上限是 1 + MAX_WRITE_QUEUE。不把「在飞」与「排队」
  // 分成两个计数器：同步连发时第一条还卡在微任务里，分开放会把它算成排队，凭空少一格。
  if (writeHolders > MAX_WRITE_QUEUE) return null
  const previous = writeTail
  let resolveOwn: () => void = () => {}
  const own = new Promise<void>((resolve) => {
    resolveOwn = resolve
  })
  writeTail = own
  writeHolders += 1
  await previous
  return () => {
    writeHolders -= 1
    resolveOwn()
  }
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

  /** 执行一条动作：幂等 / 打断 / 失败落态 / 回执。批次排队在外层 `runUiAction`（见 `./ui-batch-gate.ts`） */
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
    // 非幂等动作的同参重试按 5 秒窗挡掉（论证见 ./ui-dedupe.ts）：命中就静默丢、不回执。
    if (!spec.idempotent && !allowNonIdempotent(req.action, req.args, startedAt)) return

    // `guarded`（不可逆 / 对外系统 / 涉及凭证）：执行器调用前再要一次律师的本地确认。
    // 位置在写锁内——弹框期间别的写动作排队，此刻也还没发出任何请求。这一下只是防误点，
    // 不是批准凭据（批准在服务端审批闸门）；没有确认宿主时 fail closed，走既有 aborted 回执。
    if (spec.risk === 'guarded' && !(await confirmGuardedAction(req, spec.title))) {
      markAborted(req, '律师在二次确认里取消了')
      return
    }

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

  /**
   * 跑一步：写动作先取写锁再执行，`safe` 动作直接执行（理由见文件头）。
   *
   * 为什么单步与批次都走这里：单步路径本来没有任何排队（两条 `confirm` 各自到达、
   * 各自开跑）；批次路径虽然串行同批步骤，但**跨批**的两步照样并飞，read-modify-write
   * 一样会丢更新。写锁是唯一覆盖跨批的那道，也是同批的第二道保险。
   *
   * 排队超限：不执行、落失败、**回执**。不回执的话后端只能等到超时，模型那边看着
   * 像「动作还在跑」，于是它多半会原样重发一遍——正是这层要拦的行为。
   *
   * 打断不在这里判：排在队里也要走 `runOne`，由它按 `abortedAt` 落 `aborted`——
   * 排队不该成为绕过打断判定的路径（08 §4.5）。
   */
  const runWithWriteLock = async (req: UiActionRequest): Promise<void> => {
    if (!isWriteAction(req.action)) {
      await runOne(req)
      return
    }
    const release = await acquireWriteLock()
    if (!release) {
      const now = Date.now()
      writeRun(req.callId, { ...runMeta(req, now), state: 'error', code: 'executor_error', endedAt: now })
      ackResult(req, { outcome: 'error', code: 'executor_error', detail: WRITE_QUEUE_FULL_DETAIL })
      return
    }
    try {
      await runOne(req)
    } finally {
      release()
    }
  }

  return {
    uiToolRuns: {},
    abortedAt: null,

    runUiAction: async (req: UiActionRequest) => {
      // 同一 callId 只执行一次（论证见 ./ui-dedupe.ts）。也在排队之前挡：重放的帧不该占掉
      // 一个队位。
      if (rememberCallId(req.callId)) return
      // 多标签页：同一条动作两个标签页都收到，抢不到执行权就静默返回（不落记录、不回执）
      if (!claimUiActionExecution(req.callId)) return

      // 批次排队 / 超限 / 失败即中止的语义全在 ./ui-batch-gate.ts，这里只接四根线。
      await runThroughBatchGate(req.batchId, {
        run: () => runWithWriteLock(req),
        abort: (detail) => markAborted(req, detail),
        refuse: (detail) => {
          const now = Date.now()
          writeRun(req.callId, { ...runMeta(req, now), state: 'error', code: 'executor_error', endedAt: now })
          ackResult(req, { outcome: 'error', code: 'executor_error', detail })
        },
        // 判据看运行记录而不是返回值：runOne 有多条 return，改一处就会漏一处。
        // 只有 `ok` 才算通过；没有记录 = 什么都没执行（同参去重），不算失败。
        passed: () => {
          const run = get().uiToolRuns[req.callId]
          return !run || run.state === 'ok'
        },
      })
    },

    abortUiActions: () => {
      // 幂等：连点「停下」只记第一次的时刻，之后到达的动作都按那一刻起算
      if (get().abortedAt !== null) return
      set({ abortedAt: Date.now() })
    },
  }
}
