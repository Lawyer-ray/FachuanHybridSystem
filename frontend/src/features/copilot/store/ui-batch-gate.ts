/**
 * 界面动作的批次闸门：同批串行 / 失败即中止 / 最后一条结算完删闸门。
 *
 * 从 `store/ui-tools.ts` 拆出：`runUiAction` 里「该不该等、该不该跑」全在这里，store 只
 * 提供 `run` / `abort` / `refuse` / `passed` 四个接线动作（它要用 `set` / `get` 落记录）。
 *
 * ## 批次（`ui_action_batch`）为什么在这里排队
 *
 * 一次确认可以带 2~5 步，帧是连着到的，而每一步都要落运行记录、发回执。同批的语义
 * **有先后**（先跳页再切 stage ≠ 先切 stage 再跳页），并发执行会让审批卡上那句「将按
 * 顺序执行」变成假承诺。所以同 `batchId` 的后一条要等前一条**结算**（不是「已发起」）。
 * 不同批次互不阻塞（两批本来就是两件互不相干的事），但跨批的**写**动作仍受写锁约束
 * ——见 `store/ui-tools.ts` 文件头那一节。
 *
 * 失败即中止：同批任一步失败、或律师按下「停下」，**后续步骤一律标 aborted 并回执**，
 * 不做「跳过它继续跑剩下的」——律师看到的是「一半动了」，而模型没法判断页面停在哪。
 *
 * ## 为什么闸门在模块级而不是 state
 *
 * 批次闸门只服务执行期的排队，没有组件关心「哪一批在排队」；放进 `CopilotState` 的代价
 * 是每次动作都触发一遍全局订阅者比较。
 */

/** 同一批最多几步（与后端 `MAX_BATCH_STEPS` 对齐）：等待队列的上限，超限说明契约已漂移 */
const BATCH_LIMIT = 5

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

/** 本条所属批次的闸门；单步动作（没有批次）返回 null —— 不排队，立即执行 */
function gateOf(batchId: string | null | undefined): BatchGate | null {
  if (typeof batchId !== 'string' || batchId === '') return null
  const existing = batchGates.get(batchId)
  if (existing) return existing
  const gate: BatchGate = { accepted: 0, stopped: false, tail: Promise.resolve() }
  batchGates.set(batchId, gate)
  return gate
}

/** 一步的接线（store 提供）：闸门只决定「什么时候轮到它」，动作本身不在这里 */
export interface BatchStep {
  /** 真的执行这一步（取写锁 + `runOne` 都在 store 侧） */
  run: () => Promise<void>
  /** 同批已中止：落 aborted 并回执 */
  abort: (detail: string) => void
  /** 超出上限：落失败记录并回执（不执行） */
  refuse: (detail: string) => void
  /** 本步是否通过（store 侧看运行记录判，不看返回值） */
  passed: () => boolean
}

/**
 * 按闸门跑一步：单步动作（没有 `batchId`）直接跑，同批动作排队。
 *
 * 返回的 Promise 在本步**结算**时 resolve —— 同批后一条等的就是它。
 */
export async function runThroughBatchGate(
  batchId: string | null | undefined,
  step: BatchStep,
): Promise<void> {
  const gate = gateOf(batchId)
  if (!gate) {
    await step.run()
    return
  }
  if (gate.accepted >= BATCH_LIMIT) {
    // 契约外（后端一批最多 5 步）：既不无限排队，也不悄悄丢——留失败记录 + 回执
    step.refuse(`同一批最多 ${BATCH_LIMIT} 步，这一步没有执行`)
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
      step.abort('同批已有步骤失败或被停下，这一步没有执行')
      return
    }
    // 批次闸门已放行，再取写锁（顺序固定：先闸门、后写锁，见 store 的 `writeTail` 注释）
    await step.run()
  } finally {
    // 判据由 store 看运行记录给出（`runOne` 有多条 return，看返回值会漏）。
    if (!step.passed()) gate.stopped = true
    release()
    // 最后一条结算完就把闸门删掉（没人再等它），否则长会话按批次数无限长大
    if (batchId && gate.tail === own) batchGates.delete(batchId)
  }
}
