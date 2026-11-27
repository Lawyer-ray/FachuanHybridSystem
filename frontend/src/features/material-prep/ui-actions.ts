/**
 * 材料预处理页的 UI 动作实现 —— 约定文件（`ui-tools/discover.ts` 用 glob 扫这一层）。
 *
 * ## 为什么这条实现在页面侧，而不是 copilot 的 `UI_EXECUTORS`
 *
 * `ui_material_prep_judge` 要**真的写库**（`PUT /inbox/messages/{id}/draft`），只有本 feature
 * 知道该走哪个 API、该把草稿里的哪些字段原样带回（`setPackStatusRemote` 的保留逻辑）。
 * 放进 copilot 的内置表，等于让 copilot 的执行层 import 材料预处理页的 API 模块：
 * 两边的懒加载 chunk 互相拖，而 **copilot 从此要为每个新页面的写库动作改一次自己的代码**
 * ——「页面自己声明实现」要消灭的正是这件事。
 *
 * ## 参数不重复校验 schema，但 `typeof` 收窄必须留着
 *
 * schema 校验是 `registry.validateArgs` 的事（清单的 `argsSchema` 是唯一真相），这里再抄一遍
 * 只会多一个漂移点。但 `args` 的类型是 `Record<string, unknown>`，直接
 * `setPackStatusRemote(args.packId as number)` 就是把守卫写成 `as`——写库动作不许这么干。
 * 这段收窄挡的也不是「模型乱填」（registry 已经拦了），而是灰度期旧前端 / 挂起队列里
 * 经过一轮 JSON 往返的参数。
 */

import type { PageUiAction, UiToolOutcome } from '@/features/copilot/ui-tools/contract'
import { errMessage } from '@/lib/errors'

import { setPackStatusRemote } from './api/inbox-packs'
import type { PackStatus } from './types'

/**
 * 判决成功的广播事件名：执行器只改库，**让页面自己重拉列表**。
 *
 * 为什么走 window 事件而不是直接 invalidate：执行器可能在 copilot 那一侧跑（页面还没挂载
 * 或挂在别处），而 QueryClient 只属于页面这一侧。事件是两边都认识的唯一接口，
 * 与 `copilot/launch.ts` 同一套模式。
 */
export const PACK_STATUS_CHANGED_EVENT = 'material-prep:pack-status-changed'

/** 判决终态：`PackStatus` 里的两个终态（`todo` 是起始态，不能 judge 过去） */
export type PackJudgeTarget = Extract<PackStatus, 'done' | 'filed'>

/** 广播载荷：页面据此重拉列表，并把「改成了什么」写进 toast */
export interface PackStatusChangedDetail {
  packId: number
  status: PackJudgeTarget
}

/** 终态的中文说法：动作 detail 与页面 toast 共用一份（词与 `PACK_STAGES` 的页签标签一致） */
export const PACK_JUDGE_LABEL: Record<PackJudgeTarget, string> = {
  done: '已归案',
  filed: '不接归档',
}

/** 已收窄的判决参数 */
interface JudgeArgs {
  packId: number
  target: PackJudgeTarget
}

/** `args` → 收窄后的参数；`null` = 形状不对（调用方按 `invalid_args` 处置） */
function parseJudgeArgs(args: Record<string, unknown>): JudgeArgs | null {
  const { packId, target } = args
  if (typeof packId !== 'number' || !Number.isInteger(packId)) return null
  if (target !== 'done' && target !== 'filed') return null
  return { packId, target }
}

function invalidArgs(args: Record<string, unknown>): UiToolOutcome {
  return {
    ok: false,
    code: 'invalid_args',
    message: `材料包判决参数不合法：${JSON.stringify(args)}（要 packId 整数 + target 为 done/filed）`,
  }
}

/** 真的写库的那一步（不碰 UI）：成功给可读 detail，失败分类成 `UiToolOutcome`。 */
async function writePackStatus({ packId, target }: JudgeArgs): Promise<UiToolOutcome> {
  try {
    await setPackStatusRemote(packId, target)
    return { ok: true, detail: `材料包 ${packId} 已判为${PACK_JUDGE_LABEL[target]}` }
  } catch (error) {
    return {
      ok: false,
      code: 'executor_error',
      message: errMessage(error, '材料包判决失败，请重试'),
    }
  }
}

/**
 * 判决一个材料包。执行器与「挂起队列」的消费端（`hooks/use-material-prep-ui-actions.ts`）
 * 都调它——写库 + 失败分类只该有一份，hook 里再抄一遍就是两套错误文案。
 */
export async function judgeMaterialPack(args: Record<string, unknown>): Promise<UiToolOutcome> {
  const parsed = parseJudgeArgs(args)
  if (parsed === null) return invalidArgs(args)
  return writePackStatus(parsed)
}

export const uiActions: readonly PageUiAction[] = [
  {
    action: 'ui_material_prep_judge',
    async execute(args, ports) {
      const parsed = parseJudgeArgs(args)
      if (parsed === null) return invalidArgs(args)
      const outcome = await writePackStatus(parsed)
      // 只有真的写成功才广播：失败也广播会让页面白拉一次列表，还让「已改」的 toast
      // 出现在什么都没改的界面上。
      if (outcome.ok) {
        const detail: PackStatusChangedDetail = { packId: parsed.packId, status: parsed.target }
        ports.dispatch(PACK_STATUS_CHANGED_EVENT, detail)
      }
      return outcome
    },
  },
]
