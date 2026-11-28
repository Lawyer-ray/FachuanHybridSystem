/**
 * `guarded` 动作的**前端本地二次确认**：注册点 + 请求入口（零 React、零依赖）。
 *
 * ## 这一层是什么，不是什么
 *
 * 它是**防误点**，不是批准凭据。`guarded` 动作（不可逆 / 对外系统 / 涉及凭证）的批准
 * 由服务端审批闸门给出；这里这一下「再点一次确认」只解决「模型挑错了对象、律师手滑了」
 * 这类事故。CopilotKit 踩过的坑正是把客户端那次确认当成授权——客户端能伪造、能跳过、
 * 能被改包，所以本模块的返回值**只**用于「这一侧要不要动」，绝不回传给后端当授权证据。
 *
 * ## 为什么 fail closed（没有宿主时返回 false）
 *
 * 二次确认宿主（`hooks/use-ui-guarded-confirm` 挂的对话框）没挂载 = 没人在问律师。
 * 这时唯一安全的选择是**不执行**：宁可什么都不动、落一条 `aborted` 回执让模型知道
 * 「律师没同意」，也不能悄悄绕过那层确认把不可逆动作做掉。反过来（没有宿主就放行）
 * 只需要一次挂载失败（面板收起、路由未就绪、灰度期旧前端），删除就会静默发生。
 *
 * ## 为什么请求里带 `title` 与 `args`
 *
 * 弹框要能让律师**认出是哪一条**：`title` 是清单里的中文名，`args` 是模型真正要执行的
 * 参数（删除哪个 `packId`）。只写「AI 想做一个操作」等于让人闭眼签字。
 *
 * ## 为什么注册是「单槽 + 归属撤销」
 *
 * 宿主有两处（`CopilotPanel` 与 `AssistantPage` 共用 `useUiToolHost`），槽位只有一个。
 * 无条件 `setGuardedConfirmHandler(null)` 会让「关一下面板」把助手页刚注册的宿主一起
 * 撤掉，表现为「AI 的删除动作突然全都被拒」且没有任何报错（同 `releaseUiToolPorts`）。
 * 所以撤销按**归属**：当前槽位还是我这一份才置空。
 */

/** 一次二次确认请求：律师看到的就是这三个字段（+ 一次点击） */
export interface GuardedConfirmRequest {
  /** 动作名（`ui_material_prep_delete_pack` 之类，用于日志与将来按动作定制文案） */
  action: string
  /** 清单里的中文名（弹框标题用它，别在组件里另起一套文案） */
  title: string
  /** 模型真正要执行的参数（原样展示，不改写、不裁剪语义） */
  args: Record<string, unknown>
  /** 这次动作的 callId（排查时能把弹框与后端审计行对上） */
  callId: string
}

/** 宿主实现：弹出确认并等律师点一下。`true` = 同意执行，`false` = 取消 */
export type GuardedConfirmHandler = (req: GuardedConfirmRequest) => Promise<boolean>

/** 当前宿主（null = 没有挂载二次确认框） */
let handler: GuardedConfirmHandler | null = null
/** 「没有宿主」只 warn 一次：每次 guarded 动作都刷一条会把控制台淹掉（同 ui-action-claim） */
let warnedMissingHost = false

/**
 * 注册/撤销宿主。注册新宿主会把「没宿主」的告警标记复位——下次再没有宿主时应当再吵一次，
 * 否则「挂载过一次、后来掉了」这种最难查的故障会永远静默。
 */
export function setGuardedConfirmHandler(next: GuardedConfirmHandler | null): void {
  handler = next
  if (next !== null) warnedMissingHost = false
}

/**
 * 按归属撤销宿主：槽位还是我这一份才置空（理由见文件头「单槽 + 归属撤销」）。
 * 宿主卸载时必须调它，否则 guarded 动作会去 await 一个已经不在的对话框。
 */
export function releaseGuardedConfirmHandler(owned: GuardedConfirmHandler): void {
  if (handler === owned) handler = null
}

/**
 * 问律师一次。`true` = 同意执行（调用方继续），`false` = 不执行（调用方落 aborted）。
 *
 * 三种失败都按「没同意」处理，且**都只 warn、不抛**：调用方是写锁内的单步执行，
 * 让异常冒出去会变成一条无人处理的 rejection，而动作状态会停在 `running` 永不结算。
 */
export async function askGuardedConfirm(req: GuardedConfirmRequest): Promise<boolean> {
  const current = handler
  if (current === null) {
    if (!warnedMissingHost) {
      warnedMissingHost = true
      console.warn(
        `[ui-guarded-confirm] 没有挂载二次确认宿主：${req.action} 一律不执行（fail closed；这是防误点那一层，不许绕过）`,
      )
    }
    return false
  }
  try {
    return await current(req)
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error)
    console.warn(`[ui-guarded-confirm] 二次确认宿主异常，按「律师没同意」处理：${message}`)
    return false
  }
}

/**
 * `guarded` 动作执行前的最后一道闸：`true` = 律师点了确认（调用方继续执行）。
 *
 * 把「帧 + 清单 → 确认请求」的字段拼接收在这里，而不是散在 store 里：store 只需要一个
 * 布尔值，而「`title` 来自清单、`args`/`callId` 来自帧」这条对应关系属于本模块。
 * 刻意用结构类型而不是 import store 的类型，保持本文件零依赖（它要能被 node 单测直接加载）。
 */
export function confirmGuardedAction(
  request: { action: string; args: Record<string, unknown>; callId: string },
  title: string,
): Promise<boolean> {
  // 逐字段构造而不是 `{...request, title}`：帧上还带着 `route` / `batchId` 之类，
  // 顺手扇进去会让「二次确认请求」的形状随帧演化（宿主只需要认这四个字段）。
  return askGuardedConfirm({
    action: request.action,
    title,
    args: request.args,
    callId: request.callId,
  })
}
